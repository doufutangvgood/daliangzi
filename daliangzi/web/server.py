"""Flask 服务：把管道包成一个本地网页工具。

进度用 SSE 推给前端。分析跑在后台线程里，刷新页面不会中断。
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file, stream_with_context

from ..config import (
    ENV_FILE,
    Config,
    ensure_dirs,
    is_peak_now,
    load_env_file,
    save_env_file,
)
from ..ingest.model import Comment
from ..ingest.parse import (
    detect_mapping,
    load_from_file,
    load_from_text,
    records_to_comments,
)
from ..llm import reset_usage
from ..pipeline import STAGE_LABELS, STAGE_ORDER, analyze, prompt_fingerprint
from ..prompts_loader import list_prompts, load_prompt, save_prompt
from ..store import get_run, list_runs, new_run_id

STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------- 任务管理

@dataclass
class Job:
    job_id: str
    run_id: str
    status: str = "running"          # running / done / error
    message: str = ""
    percent: float = 0.0
    error: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    events: queue.Queue = field(default_factory=queue.Queue)
    started_at: float = field(default_factory=time.time)

    def emit(self, message: str, percent: float) -> None:
        self.message = message
        self.percent = percent
        self.events.put({"type": "progress", "message": message, "percent": round(percent * 100, 1)})

    def finish(self, summary: dict[str, Any]) -> None:
        self.status = "done"
        self.summary = summary
        self.percent = 1.0
        self.events.put({"type": "done", "summary": summary})

    def fail(self, error: str) -> None:
        self.status = "error"
        self.error = error
        self.events.put({"type": "error", "error": error})


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
_job_seq = 0


def _new_job(run_id: str) -> Job:
    global _job_seq
    with _jobs_lock:
        _job_seq += 1
        job_id = f"job-{_job_seq}"
        job = Job(job_id=job_id, run_id=run_id)
        _jobs[job_id] = job
        return job


def _get_job(job_id: str) -> Job | None:
    with _jobs_lock:
        return _jobs.get(job_id)


# ---------------------------------------------------------------- 应用

def _merge_clean_reports(a: dict, b: dict) -> dict:
    """把两次推送的清洗统计累加起来，保留完整来源记录。"""
    keys = ["原始条数", "去空", "去太短", "去灌水", "去广告", "去重复", "保留"]
    merged = {k: int(a.get(k) or 0) + int(b.get(k) or 0) for k in keys}
    notes = list(a.get("notes") or []) + list(b.get("notes") or [])
    merged["notes"] = notes
    return merged


def _cors(resp):
    """给「浏览器推送」这个入口放行跨域。

    服务本身只绑 127.0.0.1，所以外部网络到不了；放开跨域是为了让
    bilibili.com 之类的页面里的采集脚本能把数据 POST 进来。
    """
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def create_app() -> Flask:
    ensure_dirs()
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 上传上限 64MB

    # -------------------------------------------------- 静态页

    @app.get("/")
    def index():
        return send_file(STATIC_DIR / "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        target = (STATIC_DIR / filename).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
            return jsonify({"error": "not found"}), 404
        return send_file(target)

    # -------------------------------------------------- 设置

    @app.get("/api/status")
    def api_status():
        cfg = Config.load()
        peak = is_peak_now()
        return jsonify({
            "has_key": cfg.has_key,
            "masked_key": cfg.masked_key(),
            "model": cfg.model,
            "base_url": cfg.base_url,
            "batch_size": cfg.batch_size,
            "concurrency": cfg.concurrency,
            "peak": peak,
            "price": cfg.price_table(),
            "env_file": str(ENV_FILE),
            "stages": STAGE_ORDER,
            "stage_labels": STAGE_LABELS,
            "prompt_fingerprints": {
                name: prompt_fingerprint(name)
                for name in [
                    "stage1_标签", "stage2_合并", "stage4_坐标轴",
                    "stage5_陪审团", "stage5_报告",
                ]
            },
        })

    @app.post("/api/settings")
    def api_settings():
        body = request.get_json(silent=True) or {}
        updates: dict[str, str] = {}

        api_key = (body.get("api_key") or "").strip()
        if api_key:
            updates["DEEPSEEK_API_KEY"] = api_key

        for key, env_name in (
            ("model", "DEEPSEEK_MODEL"),
            ("base_url", "DEEPSEEK_BASE_URL"),
            ("batch_size", "DALIANGZI_BATCH_SIZE"),
            ("concurrency", "DALIANGZI_CONCURRENCY"),
        ):
            value = body.get(key)
            if value not in (None, ""):
                updates[env_name] = str(value).strip()

        if updates:
            save_env_file(updates)

        cfg = Config.load()
        return jsonify({"ok": True, "has_key": cfg.has_key, "masked_key": cfg.masked_key()})

    @app.post("/api/settings/test")
    def api_test_key():
        """用最小代价验证 key 能不能用。"""
        from ..llm import DeepSeekClient, LLMError, run_sync

        cfg = Config.load()
        if not cfg.has_key:
            return jsonify({"ok": False, "error": "还没有填 API Key。"}), 400
        try:
            client = DeepSeekClient(cfg)
            res = run_sync(client.complete(
                "You reply with json only.",
                '请输出 {"ok": true} 这个 json，不要有任何其他内容。',
                json_mode=True,
                max_tokens=64,
                label="连通性测试",
            ))
            return jsonify({"ok": True, "model": cfg.model, "reply": str(res.data)[:200]})
        except LLMError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 400

    # -------------------------------------------------- 导入

    @app.post("/api/import")
    def api_import():
        """接收评论：粘贴文本、上传文件、或直接传 JSON 数组。"""
        event_name = ""
        platform = ""
        text = ""
        filename = ""
        min_chars = 3

        if request.files:
            upload = next(iter(request.files.values()))
            filename = upload.filename or ""
            raw = upload.read()
            # 统一按 utf-8 读，失败退回 gbk（国内导出常见）
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
            event_name = request.form.get("event_name", "")
            platform = request.form.get("platform", "")
            min_chars = int(request.form.get("min_chars") or 3)
        else:
            body = request.get_json(silent=True) or {}
            event_name = (body.get("event_name") or "").strip()
            platform = (body.get("platform") or "").strip()
            text = body.get("text") or ""
            filename = body.get("filename") or ""
            min_chars = int(body.get("min_chars") or 3)

        if not text.strip():
            return jsonify({"error": "没有收到任何内容。"}), 400

        result = load_from_text(text, filename=filename)
        if not result.records:
            return jsonify({"error": "没能从内容里解析出任何记录。"}), 400

        mapping = result.mapping
        body_mapping = (request.get_json(silent=True) or {}).get("mapping") if not request.files else None
        if body_mapping:
            mapping = {**mapping, **{k: v for k, v in body_mapping.items() if v}}

        clean = records_to_comments(
            result.records, mapping, platform=platform, min_chars=min_chars
        )
        if not clean.comments:
            return jsonify({
                "error": "解析出来了记录，但清洗后一条都不剩。可能是正文字段选错了。",
                "source_format": result.source_format,
                "mapping": mapping,
                "clean": clean.summary(),
            }), 400

        event_name = event_name or "未命名事件"
        run_id = new_run_id(event_name)
        run = get_run(run_id)

        run.save("input", {
            "meta": {
                "event_name": event_name,
                "platform": platform,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source_format": result.source_format,
                "filename": filename,
            },
            "mapping": mapping,
            "clean_report": clean.summary(),
            "comments": [c.to_dict() for c in clean.comments],
        })

        preview = [c.to_dict() for c in clean.comments[:8]]
        return jsonify({
            "ok": True,
            "run_id": run_id,
            "count": len(clean.comments),
            "source_format": result.source_format,
            "mapping": mapping,
            "available_fields": sorted({
                k for r in result.records[:20] if isinstance(r, dict) for k in r.keys()
            }),
            "clean": clean.summary(),
            "preview": preview,
            "warnings": result.warnings,
        })

    @app.post("/api/preview")
    def api_preview():
        """只解析看结果，不建 run。用于导入前核对字段。"""
        body = request.get_json(silent=True) or {}
        text = body.get("text") or ""
        if not text.strip():
            return jsonify({"error": "内容为空。"}), 400
        result = load_from_text(text, filename=body.get("filename") or "")
        mapping = result.mapping
        if body.get("mapping"):
            mapping = {**mapping, **{k: v for k, v in body["mapping"].items() if v}}
        clean = records_to_comments(result.records, mapping, min_chars=int(body.get("min_chars") or 3))
        return jsonify({
            "mapping": mapping,
            "source_format": result.source_format,
            "available_fields": sorted({
                k for r in result.records[:50] if isinstance(r, dict) for k in r.keys()
            }),
            "total_records": len(result.records),
            "clean": clean.summary(),
            "preview": [c.to_dict() for c in clean.comments[:8]],
            "warnings": result.warnings,
        })

    # -------------------------------------------------- 浏览器直接推送

    @app.route("/api/ingest/push", methods=["POST", "OPTIONS"])
    def api_ingest_push():
        """让浏览器里的采集脚本把评论直接推进来。

        这是给「用浏览器抓评论」这个场景准备的：脚本在页面里跑，
        抓到结构化数据后 POST 到这里，建一个 run。省掉了导出文件再手工上传。

        只监听本机（服务本身绑定 127.0.0.1），并允许跨域，
        因为调用方是 bilibili.com 之类的第三方页面。

        请求体：
            {"event_name": "...", "platform": "...", "records": [ {...}, ... ]}
        records 里每条至少要有正文字段，字段名会自动识别。
        """
        if request.method == "OPTIONS":
            resp = app.make_default_options_response()
            _cors(resp)
            return resp

        body = request.get_json(silent=True) or {}
        records = body.get("records") or []
        if not isinstance(records, list) or not records:
            resp = jsonify({"error": "records 为空"})
            _cors(resp)
            return resp, 400

        event_name = (body.get("event_name") or "未命名事件").strip()
        platform = (body.get("platform") or "").strip()
        target_run_id = (body.get("run_id") or "").strip()

        mapping = detect_mapping(records)
        if body.get("mapping"):
            mapping = {**mapping, **{k: v for k, v in body["mapping"].items() if v}}
        # 调用方显式指定的 platform 优先于自动识别的列，
        # 否则记录里一个叫 source 的字段（比如视频标题）会被当成平台
        if platform:
            mapping["platform"] = None

        clean = records_to_comments(
            records, mapping,
            platform=platform,
            min_chars=int(body.get("min_chars") or 3),
        )
        if not clean.comments:
            resp = jsonify({
                "error": "推送了记录，但清洗后一条都不剩。检查正文字段是否识别正确。",
                "mapping": mapping,
                "clean": clean.summary(),
            })
            _cors(resp)
            return resp, 400

        # 追加模式：把多平台的数据汇进同一个 run，方便一起分析
        appended = False
        if target_run_id:
            try:
                run = get_run(target_run_id)
            except ValueError:
                run = None
            if run is not None and run.has("input"):
                existing = run.load("input") or {}
                old = existing.get("comments") or []
                seen = {c.get("id") for c in old}
                merged = list(old)
                for comment in clean.comments:
                    if comment.id not in seen:
                        seen.add(comment.id)
                        merged.append(comment.to_dict())

                meta = existing.get("meta") or {}
                plats = [p for p in (meta.get("platforms") or []) if p]
                if platform and platform not in plats:
                    plats.append(platform)
                meta["platforms"] = plats
                meta["platform"] = "+".join(plats) if plats else platform

                existing["comments"] = merged
                existing["meta"] = meta
                existing["clean_report"] = _merge_clean_reports(
                    existing.get("clean_report") or {}, clean.summary()
                )
                run.save("input", existing)
                run_id = target_run_id
                appended = True

        if not appended:
            run_id = new_run_id(event_name)
            run = get_run(run_id)

        if not appended:
            run.save("input", {
                "meta": {
                    "event_name": event_name,
                    "platform": platform,
                    "platforms": [platform] if platform else [],
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source_format": "browser-push",
                    "filename": "",
                },
                "mapping": mapping,
                "clean_report": clean.summary(),
                "comments": [c.to_dict() for c in clean.comments],
            })

        total = len((run.load("input") or {}).get("comments") or [])
        resp = jsonify({
            "ok": True,
            "run_id": run_id,
            "appended": appended,
            "received": len(records),
            "count": len(clean.comments),
            "total_in_run": total,
            "mapping": mapping,
            "clean": clean.summary(),
        })
        _cors(resp)
        return resp

    # -------------------------------------------------- 浏览器直接推送 · 结束

    # -------------------------------------------------- 运行列表

    @app.get("/api/runs")
    def api_runs():
        return jsonify({"runs": list_runs()})

    @app.get("/api/runs/<run_id>")
    def api_run_detail(run_id: str):
        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        if not run.has("input"):
            return jsonify({"error": "这个运行不存在。"}), 404

        input_payload = run.load("input") or {}
        stats = run.load("stats") or {}
        axis = run.load("axis") or {}
        jury = run.load("jury") or {}
        report = run.load("report") or {}
        canon = run.load("canonical") or {}
        labels = run.load("labels") or {}

        # 老版本的 stats 是在坐标轴之前落盘的，里面没有 x。
        # 这里把坐标轴的产物补回去，保证界面拿到的数据是完整的。
        positions = {
            p.get("canonical"): p.get("x")
            for p in (axis.get("positions") or [])
            if isinstance(p, dict)
        }
        alignments = {
            a.get("canonical"): (a.get("left_affinity"), a.get("right_affinity"))
            for a in (axis.get("alignments") or [])
            if isinstance(a, dict)
        }
        for stance in stats.get("stances") or []:
            canonical = stance.get("canonical")
            if canonical in positions and stance.get("x") is None:
                stance["x"] = positions[canonical]
            if canonical in alignments:
                if stance.get("left_affinity") is None:
                    stance["left_affinity"] = alignments[canonical][0]
                if stance.get("right_affinity") is None:
                    stance["right_affinity"] = alignments[canonical][1]

        labelled = labels.get("labels") or {}
        return jsonify({
            "run_id": run_id,
            "meta": input_payload.get("meta") or {},
            "clean_report": input_payload.get("clean_report") or {},
            "mapping": input_payload.get("mapping") or {},
            "comments": (input_payload.get("comments") or [])[:500],
            "comment_total": len(input_payload.get("comments") or []),
            "stats": stats,
            "axis": axis,
            "jury": jury,
            "report": report.get("markdown") or "",
            "canonical": {"merge_notes": canon.get("merge_notes", ""), "notes": canon.get("notes") or []},
            "label_notes": labels.get("notes") or [],
            "labelled_total": len(labelled),
            "has": {stage: run.has(stage) for stage in STAGE_ORDER},
        })

    @app.delete("/api/runs/<run_id>")
    def api_delete_run(run_id: str):
        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        run.delete()
        return jsonify({"ok": True})

    @app.get("/api/runs/<run_id>/comments/<comment_id>")
    def api_comment_detail(run_id: str, comment_id: str):
        """下钻：看某条评论被捞出了什么标签。"""
        run = get_run(run_id)
        labels = (run.load("labels") or {}).get("labels") or {}
        input_payload = run.load("input") or {}
        comment = next(
            (c for c in (input_payload.get("comments") or []) if c.get("id") == comment_id),
            None,
        )
        return jsonify({"comment": comment, "labels": labels.get(comment_id) or []})

    @app.get("/api/export/<run_id>.md")
    def api_export_md(run_id: str):
        run = get_run(run_id)
        report = run.load("report") or {}
        markdown = report.get("markdown") or ""
        if not markdown:
            return jsonify({"error": "还没有生成报告。"}), 404
        path = run.save_text("报告.md", markdown)
        return send_file(path, as_attachment=True, download_name=f"{run_id}-立场一览.md")

    # -------------------------------------------------- 提示词

    @app.get("/api/prompts")
    def api_prompts():
        return jsonify({"prompts": list_prompts()})

    @app.get("/api/prompts/<name>")
    def api_prompt_get(name: str):
        try:
            return jsonify({"name": name, "content": load_prompt(name)})
        except FileNotFoundError:
            return jsonify({"error": "提示词不存在"}), 404

    @app.put("/api/prompts/<name>")
    def api_prompt_put(name: str):
        body = request.get_json(silent=True) or {}
        content = body.get("content")
        if not isinstance(content, str):
            return jsonify({"error": "缺少 content"}), 400
        try:
            save_prompt(name, content)
        except FileNotFoundError:
            return jsonify({"error": "提示词不存在"}), 404
        return jsonify({"ok": True, "fingerprint": prompt_fingerprint(name)})

    # -------------------------------------------------- 分析

    @app.get("/api/runs/<run_id>/labels")
    def api_labels_preview(run_id: str):
        """把「评论 → 标签」的对应关系批量列出来，用来人工核对捞取质量。

        试跑几十条之后，用这个看模型到底捞出了什么词、有没有在发明分类。
        """
        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        if not run.has("input"):
            return jsonify({"error": "这个运行不存在。"}), 404

        limit = min(500, max(1, int(request.args.get("limit") or 60)))
        only_labelled = request.args.get("only_labelled") == "1"

        labels = (run.load("labels") or {}).get("labels") or {}
        input_payload = run.load("input") or {}
        comments = input_payload.get("comments") or []

        rows = []
        for c in comments:
            labs = labels.get(c.get("id"))
            if labs is None:
                continue                       # 还没跑过
            if only_labelled and not labs:
                continue
            rows.append({
                "id": c.get("id"),
                "text": c.get("text", ""),
                "likes": c.get("likes", 0),
                "labels": labs,
            })
            if len(rows) >= limit:
                break

        total_labelled = len(labels)
        with_labels = sum(1 for v in labels.values() if v)
        # 观点是主键；圈内词只是附带展示
        opinions = sorted({
            lab.get("opinion", "")
            for v in labels.values() for lab in v if lab.get("opinion")
        })
        terms = sorted({
            lab.get("term", "")
            for v in labels.values() for lab in v if lab.get("term")
        })

        return jsonify({
            "rows": rows,
            "labelled": total_labelled,
            "total_comments": len(comments),
            "with_labels": with_labels,
            "empty": total_labelled - with_labels,
            "distinct_opinions": len(opinions),
            "top_opinions": opinions[:80],
            "distinct_terms": len(terms),
            "top_terms": terms[:80],
            "coverage_complete": total_labelled >= len(comments),
        })

    @app.post("/api/analyze")
    def api_analyze():
        body = request.get_json(silent=True) or {}
        run_id = body.get("run_id") or ""
        redo = list(body.get("redo") or [])
        stop_after = body.get("stop_after") or None
        try:
            sample_limit = int(body.get("sample_limit") or 0)
        except (TypeError, ValueError):
            sample_limit = 0

        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        if not run.has("input"):
            return jsonify({"error": "这个运行还没有导入评论。"}), 404

        cfg = Config.load()
        if not cfg.has_key:
            return jsonify({"error": "还没有配置 DeepSeek API Key。请点右上角「设置」填入。"}), 400

        input_payload = run.load("input") or {}
        comments = [
            Comment(
                id=c.get("id", ""),
                text=c.get("text", ""),
                likes=int(c.get("likes") or 0),
                platform=c.get("platform", ""),
                author=c.get("author", ""),
            )
            for c in (input_payload.get("comments") or [])
        ]
        event_name = (input_payload.get("meta") or {}).get("event_name", "")

        job = _new_job(run_id)

        def _run() -> None:
            try:
                reset_usage()
                result = analyze(
                    run, comments, cfg,
                    event_name=event_name,
                    redo=redo,
                    stop_after=stop_after,
                    sample_limit=sample_limit,
                    progress=job.emit,
                )
                from ..llm import get_usage

                job.finish({
                    "run_id": run_id,
                    "cost": round(result.cost, 4),
                    "elapsed": round(result.elapsed, 1),
                    "reused": result.reused,
                    "recomputed": result.recomputed,
                    "usage": get_usage(),
                    "sampling": result.sampling,
                    "stance_count": len(result.stats.stances) if result.stats else 0,
                })
            except Exception as exc:  # noqa: BLE001 - 后台线程必须兜住所有异常
                # 失败也可能已经花掉了一部分钱，如实告诉用户
                from ..llm import get_usage

                usage = get_usage()
                spent = cfg.cost_of(
                    usage.get("cache_hit", 0), usage.get("cache_miss", 0), usage.get("output", 0)
                )
                message = f"{type(exc).__name__}: {exc}"
                if spent > 0:
                    message += f"（本次已消耗约 {spent:.4f} 元，已完成的阶段产物已保留，重跑时会复用）"
                job.fail(message)
                traceback.print_exc()

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True, "job_id": job.job_id, "run_id": run_id})

    @app.get("/api/analyze/stream")
    def api_analyze_stream():
        job_id = request.args.get("job_id", "")
        job = _get_job(job_id)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404

        @stream_with_context
        def _gen():
            # 先补发当前状态，避免前端连上来之前的事件丢了
            yield f"data: {json.dumps({'type': 'progress', 'message': job.message, 'percent': round(job.percent * 100, 1)}, ensure_ascii=False)}\n\n"
            if job.status == "done":
                yield f"data: {json.dumps({'type': 'done', 'summary': job.summary}, ensure_ascii=False)}\n\n"
                return
            if job.status == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': job.error}, ensure_ascii=False)}\n\n"
                return

            while True:
                try:
                    event = job.events.get(timeout=20)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("done", "error"):
                    return

        return Response(_gen(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        })

    # -------------------------------------------------- 干跑：发出前先看

    @app.post("/api/dry-run")
    def api_dry_run():
        """把将要发给 DeepSeek 的请求原样展示出来，不真的发。

        刚配好 Key、准备第一次花钱之前，用这个确认请求体长什么样。
        """
        from ..config import THINKING_BY_STAGE
        from ..llm import build_payload
        from ..pipeline.stage1_labels import _build_user_prompt
        from ..prompts_loader import load_prompt

        body = request.get_json(silent=True) or {}
        run_id = body.get("run_id") or ""
        stage = body.get("stage") or "labels"

        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        if not run.has("input"):
            return jsonify({"error": "这个运行不存在。"}), 404

        input_payload = run.load("input") or {}
        cfg = Config.load()
        event_name = (input_payload.get("meta") or {}).get("event_name", "")

        comments = [
            Comment(id=c.get("id", ""), text=c.get("text", ""), likes=int(c.get("likes") or 0))
            for c in (input_payload.get("comments") or [])
        ]
        if not comments:
            return jsonify({"error": "没有评论。"}), 404

        batch = comments[: cfg.batch_size]

        if stage == "labels":
            system = load_prompt("stage1_标签")
            user = _build_user_prompt(batch)
            json_mode = True
            max_tokens = cfg.max_tokens
        elif stage == "canonical":
            system = load_prompt("stage2_合并")
            labels = (run.load("labels") or {}).get("labels") or {}
            opinions = sorted({
                lab.get("opinion", "")
                for labs in labels.values() for lab in labs if lab.get("opinion")
            })
            inventory = "\n".join(f"{o} (?) 倾向:? | 代表: （此处省略）" for o in opinions[:50])
            user = (f"事件：{event_name}\n\n观点清单（共 {len(opinions)} 个，此处只展示前 50 个）：\n\n"
                    f"{inventory}\n\n请把以上观点归纳成立场类别，只输出 JSON。")
            json_mode = True
            max_tokens = 16384
        else:
            return jsonify({"error": f"暂不支持预览阶段：{stage}"}), 400

        payload = build_payload(
            cfg, system, user,
            json_mode=json_mode,
            max_tokens=max_tokens,
            thinking=THINKING_BY_STAGE.get(stage),
        )

        # Key 只露出首尾，别在界面上回显完整密钥
        preview = dict(payload)
        preview["messages"] = [
            {"role": "system", "content": system, "字符数": len(system)},
            {"role": "user", "content": user, "字符数": len(user)},
        ]

        return jsonify({
            "url": f"{cfg.base_url.rstrip('/')}/chat/completions",
            "headers": {
                "Authorization": f"Bearer {cfg.masked_key() or '<未配置>'}",
                "Content-Type": "application/json",
            },
            "payload": preview,
            "model": cfg.model,
            "thinking": THINKING_BY_STAGE.get(stage),
            "batch_size": len(batch),
            "note": (
                "这是「捞标签」阶段第一个批次的真实请求体。"
                "注意 thinking 被显式关掉了 —— 这一阶段是机械抽取，"
                "开着思考模式只会白烧输出 token。"
                if stage == "labels" else
                "这是「语义合并」阶段的请求体，思考强度为 low。"
            ),
        })

    # -------------------------------------------------- 成本预估

    @app.post("/api/estimate")
    def api_estimate():
        body = request.get_json(silent=True) or {}
        run_id = body.get("run_id") or ""
        try:
            run = get_run(run_id)
        except ValueError:
            return jsonify({"error": "非法 run_id"}), 400
        if not run.has("input"):
            return jsonify({"error": "这个运行不存在。"}), 404
        input_payload = run.load("input") or {}
        comments = input_payload.get("comments") or []
        if not comments:
            return jsonify({"error": "没有评论可估算。"}), 404

        try:
            sample_limit = int(body.get("sample_limit") or 0)
        except (TypeError, ValueError):
            sample_limit = 0

        cfg = Config.load()
        est = estimate_cost(
            comments, cfg,
            redo=list(body.get("redo") or []),
            run=run,
            sample_limit=sample_limit,
        )
        return jsonify(est)

    return app


# ---------------------------------------------------------------- 成本预估

def _tokens(text: str) -> int:
    """粗略估 token：中文约 1 字 0.6 token，英文约 4 字符 1 token。

    只是量级估算，用来给用户一个心理预期。
    """
    chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = max(0, len(text) - chinese)
    return int(chinese * 0.6 + other / 4)


def estimate_cost(
    comments: list[dict],
    cfg: Config,
    *,
    redo: list[str],
    run,
    sample_limit: int = 0,
) -> dict:
    """估算这次要花多少钱。已经跑过的阶段不算钱。

    缓存模型按官方规则来：缓存要求**完整匹配缓存前缀单元**，
    而公共前缀要等系统检测到之后才落盘。官方例二说得很清楚 ——
    前两次请求都不命中，第三次才开始命中。并发跑的时候，
    **第一波请求全部是冷的**。
    """
    from ..config import THINKING_BY_STAGE

    price = cfg.price_table()
    total_imported = len(comments)
    if sample_limit > 0:
        comments = comments[:sample_limit]      # 样本量影响 token 估算，取前 N 条近似
    batch = max(1, cfg.batch_size)
    n = len(comments)
    batches = (n + batch - 1) // batch

    # 思考模式会额外产生思维链 token，按输出价计费。
    # 这些系数是按「推理 token 相对于回答 token 的倍数」估的。
    thinking_overhead = {"disabled": 0.0, "low": 0.8, "high": 3.0, "max": 6.0}

    def out_tokens(stage: str, base: int) -> int:
        effort = THINKING_BY_STAGE.get(stage, "high")
        return int(base * (1 + thinking_overhead.get(effort, 3.0)))

    # ---- 阶段一：捞标签 ----
    system1 = _tokens(load_prompt("stage1_标签"))
    per_comment = sum(_tokens(c.get("text", "")) for c in comments[:200]) / max(1, min(200, n))
    body1 = int(per_comment * n) + 30 * n          # 评论正文永远是未命中
    cold_wave = min(batches, max(1, cfg.concurrency))   # 第一波请求无缓存可命中
    miss1 = system1 * cold_wave + body1
    hit1 = system1 * max(0, batches - cold_wave)
    out1 = out_tokens("labels", 60 * n)            # 每条评论的标签 JSON

    # ---- 阶段二：语义合并（只喂去重标签词，按经验约为评论数的 6%）----
    terms = max(20, int(n * 0.06))
    miss2 = _tokens(load_prompt("stage2_合并")) + terms * 45
    out2 = out_tokens("canonical", terms * 30)

    # ---- 阶段四：坐标轴 ----
    miss4 = _tokens(load_prompt("stage4_坐标轴")) + 60 * 40
    out4 = out_tokens("axis", 3000)

    # ---- 阶段五：陪审团 + 报告 ----
    miss5 = _tokens(load_prompt("stage5_陪审团")) + 60 * 60
    out5 = out_tokens("jury", 60 * 120)
    miss6 = _tokens(load_prompt("stage5_报告")) + 12000
    out6 = out_tokens("report", 6000)

    stages = {
        "labels": {"hit": hit1, "miss": miss1, "out": out1},
        "canonical": {"hit": 0, "miss": miss2, "out": out2},
        "axis": {"hit": 0, "miss": miss4, "out": out4},
        "jury": {"hit": 0, "miss": miss5, "out": out5},
        "report": {"hit": 0, "miss": miss6, "out": out6},
    }

    reuse_map = {"labels": "labels", "canonical": "canonical", "axis": "axis", "jury": "jury", "report": "report"}
    rows = []
    total = 0.0
    for stage in STAGE_ORDER:
        if stage == "stats":
            continue
        already = run.has(reuse_map[stage]) and stage not in redo
        s = stages.get(stage)
        if not s:
            continue
        cost = cfg.cost_of(s["hit"], s["miss"], s["out"])
        if already:
            cost = 0.0
        else:
            total += cost
        rows.append({
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage),
            "reused": already,
            "thinking": THINKING_BY_STAGE.get(stage, "high"),
            "tokens": s["hit"] + s["miss"] + s["out"],
            "cost": round(cost, 4),
        })

    if batches <= cold_wave:
        cache_note = (
            f"本次只有 {batches} 批，并发 {cfg.concurrency} 会让它们几乎同时发出，"
            "所以**一批都命中不了缓存** —— 缓存要等前序请求结束才落盘。"
            "评论量大到批次数超过并发数之后，后面的波次才会开始命中。"
        )
    else:
        cache_note = (
            f"前 {cold_wave} 批（对应并发 {cfg.concurrency}）无缓存可命中，"
            f"之后 {batches - cold_wave} 批会命中系统提示词的缓存。"
        )

    return {
        "comment_count": n,
        "imported_count": total_imported,
        "sample_limit": sample_limit,
        "sampled": sample_limit > 0 and total_imported > sample_limit,
        "batches": batches,
        "cold_wave": cold_wave,
        "peak": is_peak_now(),
        "price": price,
        "rows": rows,
        "total": round(total, 4),
        "cache_note": cache_note,
        "note": (
            "当前是高峰时段（工作日 9-12、14-18），价格是空闲时段的两倍。"
            "等到空闲时段跑能省一半。"
            if is_peak_now() else
            "当前是空闲时段，价格已经是高峰时段的一半。"
        ),
    }
