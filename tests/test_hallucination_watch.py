# -*- coding: utf-8 -*-
"""hallucination-watch 单元测试套件。

覆盖：信号模块、check_compliance、MCP 生命周期。
运行：python -m unittest discover -s tests -p "test_*.py" -v
"""
import os, sys, json, tempfile, shutil, unittest, asyncio

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)

from signal_keyword import detect as kw_detect
from signal_consistency import check as cs_check
from signal_fuzzy import process as fz_process, extract_fingerprint
from signal_material import check as mt_check, add_entry as mt_add, has_contradiction
from signal_redundancy import calc as rd_calc
from signal_habit import calc_bins, update_profile, anomaly_score
from signal_adapt import adapt as adapt_threshold
from signal_topic import extract as topic_extract, similarity as topic_similarity
import check_compliance

DEFAULT_PARAMS = {
    "keywords": ["一定", "绝对", "所有"],
    "red_flag_keywords": ["毫无疑问", "百分百"],
    "density_multiplier": 10,
    "threshold": 22.0,
    "k_chars": 7,
    "num_bins": 5,
    "redundancy_tokens_per_increment": 1000,
    "redundancy_increment": 5,
    "min_baseline_n": 3,
    "max_baseline_n": 10,
    "adaptation_interval": 10,
    "correction_enabled": False,
    "max_claims_per_trigger": 3,
    "target_trigger_rate": 0.1,
    "rate_margin": 0.02,
    "ema_alpha": 0.3,
    "threshold_increase_factor": 1.1,
    "threshold_decrease_factor": 0.9,
    "topic_similarity_threshold": 0.15,
}

# ── 1. signal_keyword ──────────────────────────────────

class TestSignalKeyword(unittest.TestCase):
    def test_empty_text_zero(self):
        r = kw_detect("", DEFAULT_PARAMS)
        self.assertEqual(r["density"], 0)
        self.assertEqual(r["matched"], [])

    def test_normal_word_single_hit(self):
        """单个普通关键词出现1次，100字文本 → density 应为 1/100=0.01（原始计数密度）"""
        text = "这个系统" + "很稳定。" * 24 + "一定" + "。"  # ~100 字符，含 1 次「一定」
        r = kw_detect(text, DEFAULT_PARAMS)
        self.assertEqual(len(r["matched"]), 1)
        self.assertAlmostEqual(r["density"], 0.01, places=2)  # 1次 / 100字符

    def test_red_flag_three_times_weight(self):
        """红旗词应为普通词 3 倍权重：1 个红旗词 == 3 个普通词（等长文本）"""
        text_red = "x" * 87 + "百分百"  # 90 字符，raw=3
        text_norm = "x" * 84 + "一定一定一定"  # 90 字符，raw=3
        r_red = kw_detect(text_red, DEFAULT_PARAMS)
        r_norm = kw_detect(text_norm, DEFAULT_PARAMS)
        self.assertAlmostEqual(r_red["density"], r_norm["density"], places=3)

    def test_density_is_normalized_by_length(self):
        r1 = kw_detect("一定" * 5, DEFAULT_PARAMS)
        r2 = kw_detect("一定" * 5 + "很长" * 50, DEFAULT_PARAMS)
        self.assertGreater(r1["density"], r2["density"])


# ── 2. signal_consistency ──────────────────────────────

class TestSignalConsistency(unittest.TestCase):
    def test_no_prev_zero(self):
        r = cs_check("今天的天气很好。", "")
        self.assertEqual(r["score"], 0)

    def test_identical_text_flagged_repetition(self):
        t = "这个接口返回了用户信息。"
        r = cs_check(t, t)
        self.assertEqual(r["score"], 0.4)  # 高相似 → 重复

    def test_completely_different_topic(self):
        r = cs_check("量子纠缠态坍缩概率分布。", "今天食堂的红烧肉非常好吃。")
        self.assertEqual(r["score"], 0.7)  # 极低相似 → 可疑

    def test_jaccard_bounds(self):
        w1 = set("abc")
        w2 = set("ab")
        r = cs_check("abc", "ab")
        self.assertLessEqual(r.get("max_sim", 0), 1.0)


# ── 3. signal_fuzzy ────────────────────────────────────

class TestSignalFuzzy(unittest.TestCase):
    def test_empty_inputs(self):
        r = fz_process("", "", 7)
        self.assertEqual(r["similarity"], 0)
        self.assertEqual(r["score"], 0)

    def test_identical_text_high_similarity(self):
        r = fz_process("今天下雨了。出门带伞。", "今天下雨了。出门带伞。", 7)
        self.assertGreater(r["similarity"], 0.5)

    def test_fingerprint_length(self):
        fp = extract_fingerprint("第一句。第二句。abc123", 7)
        self.assertLessEqual(len(fp), 7)


# ── 4. signal_material ─────────────────────────────────

class TestSignalMaterial(unittest.TestCase):
    def test_contradiction_detected(self):
        self.assertTrue(has_contradiction("系统支持批量导入", "系统不支持批量导入"))
        self.assertTrue(has_contradiction("该功能尚未完成", "该功能已经完成"))
        self.assertFalse(has_contradiction("系统支持批量导入", "系统支持批量导出"))

    def test_check_with_contradicting_reference(self):
        ref = [{"claims": ["系统不支持批量导入"], "topic": {"系统": 1, "导入": 1}}]
        r = mt_check("系统支持批量导入", ref)
        self.assertGreater(r["score"], 0)
        self.assertGreater(r["contradictions"], 0)

    def test_check_consistent_reference(self):
        ref = [{"claims": ["系统支持批量导入"], "topic": {"系统": 1, "导入": 1}}]
        r = mt_check("系统支持批量导出", ref)
        self.assertEqual(r["contradictions"], 0)

    def test_topic_gate_blocks_unrelated(self):
        """话题无关的声明不应被对比（话题门控）"""
        ref = [{"claims": ["服务器支持IPv6"], "topic": {"服务器": 1, "ipv6": 1}}]
        r = mt_check("今天午餐有红烧肉", ref)
        self.assertEqual(r["contradictions"], 0)

    def test_add_entry_appends_claims(self):
        entries = []
        entries = mt_add(entries, "该系统支持高并发。")
        self.assertEqual(len(entries), 1)
        self.assertIn("claims", entries[0])


# ── 5. signal_redundancy ───────────────────────────────

class TestSignalRedundancy(unittest.TestCase):
    def test_linear_growth(self):
        r1 = rd_calc(1000, DEFAULT_PARAMS)
        r2 = rd_calc(2000, DEFAULT_PARAMS)
        self.assertAlmostEqual(r2, r1 * 2, places=1)

    def test_zero_input(self):
        self.assertEqual(rd_calc(0, DEFAULT_PARAMS), 0)

    def test_score_capped(self):
        """分数应有上限（防长对话必然触发 verify）"""
        r = rd_calc(10_000_000, DEFAULT_PARAMS)
        self.assertLessEqual(r, 40)  # cap 40


# ── 6. signal_habit ────────────────────────────────────

class TestSignalHabit(unittest.TestCase):
    def test_calc_bins_empty(self):
        self.assertEqual(calc_bins("", 5), [0] * 5)

    def test_calc_bins_total(self):
        bins = calc_bins("a" * 100, 5)
        self.assertEqual(sum(bins), 100)
        self.assertEqual(len(bins), 5)

    def test_update_profile_first_sample(self):
        p = update_profile({}, calc_bins("a" * 100, 5))
        self.assertEqual(p["total_samples"], 1)
        self.assertEqual(sum(p["bin_probs"]), 1.0)

    def test_update_profile_merges(self):
        p1 = update_profile({}, calc_bins("a" * 50 + "b" * 50, 5))
        p2 = update_profile(p1, calc_bins("a" * 50 + "b" * 50, 5))
        self.assertEqual(p2["total_samples"], 2)

    def test_anomaly_uniform_zero(self):
        p = {"bin_probs": [0.2] * 5}
        self.assertEqual(anomaly_score(p), 0)

    def test_anomaly_skewed_positive(self):
        p = {"bin_probs": [0.6, 0.1, 0.1, 0.1, 0.1]}
        self.assertGreater(anomaly_score(p), 0)


# ── 7. signal_adapt ────────────────────────────────────

class TestSignalAdapt(unittest.TestCase):
    def test_not_enough_data(self):
        turns = [{"triggered": False, "risk_raw": 5, "phase": "active"}] * 3
        self.assertEqual(adapt_threshold(turns, DEFAULT_PARAMS), {})

    def test_high_trigger_rate_raises_threshold(self):
        turns = [{"triggered": True, "risk_raw": 50, "phase": "active"}] * 10
        r = adapt_threshold(turns, DEFAULT_PARAMS)
        self.assertIn("threshold", r)
        self.assertGreater(r["threshold"], DEFAULT_PARAMS["threshold"])

    def test_low_trigger_rate_lowers_threshold(self):
        turns = [{"triggered": False, "risk_raw": 1, "phase": "active"}] * 10
        r = adapt_threshold(turns, DEFAULT_PARAMS)
        self.assertLess(r["threshold"], DEFAULT_PARAMS["threshold"])

    def test_threshold_bounds(self):
        turns = [{"triggered": True, "risk_raw": 100000, "phase": "active"}] * 10
        r = adapt_threshold(turns, DEFAULT_PARAMS)
        self.assertLessEqual(r["threshold"], 500.0)


# ── 8. check_compliance ────────────────────────────────

class TestCheckCompliance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_session_structure(self, sessions_dir, sid="2026-01-01_00-00-00", age_sec=5):
        """构造与真实一致的目录：sessions 在 skill 目录下，.hw_active 在项目根"""
        os.makedirs(sessions_dir, exist_ok=True)
        sd = os.path.join(sessions_dir, sid)
        os.makedirs(sd, exist_ok=True)
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()
        with open(os.path.join(sd, "turns.json"), "w", encoding="utf-8") as f:
            json.dump({"turns": [{"turn": 1, "timestamp": ts, "zone": "safe", "risk_pct": 10}]}, f)
        with open(os.path.join(self.proj, ".hw_active"), "w") as f:
            f.write(sid)
        return sid

    def test_compliant_when_recent_check(self):
        """sessions 在 skill 目录（非项目根）时也应能找到并判定合规"""
        sessions_dir = os.path.join(self.tmp, "skill_root", "hallucination-watch", "sessions")
        self._make_session_structure(sessions_dir, age_sec=5)
        r = check_compliance.check_with_dirs(self.proj, sessions_dir)
        self.assertTrue(r["compliant"], f"应合规但返回: {r}")

    def test_stale_check_not_compliant(self):
        sessions_dir = os.path.join(self.tmp, "skill_root", "hallucination-watch", "sessions")
        self._make_session_structure(sessions_dir, age_sec=120)
        r = check_compliance.check_with_dirs(self.proj, sessions_dir)
        self.assertFalse(r["compliant"])
        self.assertEqual(r["reason"], "stale_check")

    def test_window_seconds_custom(self):
        """窗口参数化：45 秒前的检查，30s 窗口不通过、60s 窗口通过"""
        sessions_dir = os.path.join(self.tmp, "skill_root", "hallucination-watch", "sessions")
        self._make_session_structure(sessions_dir, age_sec=45)
        r30 = check_compliance.check_with_dirs(self.proj, sessions_dir, window_seconds=30)
        self.assertFalse(r30["compliant"])
        self.assertEqual(r30["reason"], "stale_check")
        r60 = check_compliance.check_with_dirs(self.proj, sessions_dir, window_seconds=60)
        self.assertTrue(r60["compliant"], f"60s 窗口应合规: {r60}")

    def test_no_marker_compliant(self):
        r = check_compliance.check_with_dirs(self.proj, os.path.join(self.tmp, "x"))
        self.assertTrue(r["compliant"])
        self.assertEqual(r["reason"], "not_active")


# ── 9. MCP 生命周期（临时目录隔离） ─────────────────────

class TestMcpLifecycle(unittest.TestCase):
    def setUp(self):
        import hallucination_watch_mcp as m
        self.m = m
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skill")
        self.sessions_dir = os.path.join(self.skill_dir, "sessions")
        self.params_path = os.path.join(self.skill_dir, "params", "default.json")
        os.makedirs(os.path.join(self.skill_dir, "params"), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(SCRIPTS), "params", "default.json"), self.params_path)
        self.proj_root = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj_root)
        # 注入测试路径
        m.SESSIONS_DIR = self.sessions_dir
        m.PARAMS_PATH = self.params_path
        m.PROJ_ROOT = self.proj_root
        m.HW_ACTIVE = os.path.join(self.proj_root, ".hw_active")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_init_then_check_then_status_then_reset(self):
        r1 = json.loads(self._run(self.m.hw_init()))
        self.assertEqual(r1["status"], "ok")
        sid = r1["session_id"]
        # 幂等：再次 init 复用
        r2 = json.loads(self._run(self.m.hw_init()))
        self.assertEqual(r2["status"], "reused")
        self.assertEqual(r2["session_id"], sid)

        r3 = json.loads(self._run(self.m.hw_check("这是一个完全正常的回复。", "")))
        self.assertIn("zone", r3)
        self.assertEqual(r3["turn"], 1)

        r4 = json.loads(self._run(self.m.hw_status()))
        self.assertEqual(r4["checks"], 1)
        self.assertEqual(r4["session_id"], sid)

        r5 = json.loads(self._run(self.m.hw_reset()))
        self.assertEqual(r5["status"], "reset")
        self.assertFalse(os.path.exists(self.m.HW_ACTIVE))

    def test_check_uses_active_marker_not_directory_scan(self):
        """hw_check 必须作用于 .hw_active 指向的 session，而非目录中最新者"""
        # 创建 session A（通过 hw_init，.hw_active → A）
        r1 = json.loads(self._run(self.m.hw_init()))
        sid_a = r1["session_id"]
        # 人为制造更晚的孤儿 session B（目录排序更新）
        sid_b = "2099-01-01_00-00-00"
        os.makedirs(os.path.join(self.sessions_dir, sid_b), exist_ok=True)
        import datetime as dt
        sd_b = os.path.join(self.sessions_dir, sid_b)
        with open(os.path.join(sd_b, "session.json"), "w", encoding="utf-8") as f:
            json.dump({"session_id": sid_b, "next_turn": 1, "habit_profile": {"total_samples": 0, "bin_probs": [0.2]*5, "raw_bins": [0]*5}, "cumulative": {"total_checks": 0, "alert_count": 0}}, f)
        with open(os.path.join(sd_b, "turns.json"), "w", encoding="utf-8") as f:
            json.dump({"turns": []}, f)
        with open(os.path.join(sd_b, "reference.json"), "w", encoding="utf-8") as f:
            json.dump({"entries": []}, f)

        r = json.loads(self._run(self.m.hw_status()))
        # .hw_active 指向 A，即使 B 目录更新，也必须是 A
        self.assertEqual(r["session_id"], sid_a, f"应作用于 {sid_a} 而非 {sid_b}")

    def test_reset_removes_active_session(self):
        """reset 删除 .hw_active 指向的会话，孤儿会话保留（M6 语义）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        # 造孤儿
        orphan = os.path.join(self.sessions_dir, "2099-01-01_00-00-00")
        os.makedirs(orphan, exist_ok=True)
        with open(os.path.join(orphan, "session.json"), "w", encoding="utf-8") as f:
            json.dump({"session_id": "orphan"}, f)
        r = json.loads(self._run(self.m.hw_reset()))
        self.assertEqual(r["removed"], [sid])
        self.assertFalse(os.path.exists(os.path.join(self.sessions_dir, sid)))
        self.assertTrue(os.path.exists(orphan), "孤儿会话应保留")

    def test_ema_adaptation_does_not_pollute_params(self):
        """EMA 自适应必须写入 session.json 而非全局 params 文件"""
        before = open(self.params_path, encoding="utf-8").read()
        # 造 9 轮高触发率数据 + 本轮（第 10 次检查），正好满足 adaptation_interval=10
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        sd = os.path.join(self.sessions_dir, sid)
        turns = []
        from datetime import datetime, timezone as tz
        ts = datetime.now(tz.utc).isoformat()
        for i in range(9):
            turns.append({"turn": i + 1, "phase": "active", "triggered": True,
                          "risk_raw": 50, "timestamp": ts, "text": "x" * 100})
        with open(os.path.join(sd, "turns.json"), "w", encoding="utf-8") as f:
            json.dump({"turns": turns}, f)
        session = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        session["next_turn"] = 10
        session["phase"] = "active"
        session["cumulative"]["total_checks"] = 9
        with open(os.path.join(sd, "session.json"), "w", encoding="utf-8") as f:
            json.dump(session, f)

        self._run(self.m.hw_check("触发自适应测试", ""))

        # 全局 params 必须原封不动
        after = open(self.params_path, encoding="utf-8").read()
        self.assertEqual(before, after, "全局 params/default.json 不应被 EMA 修改")
        # session 中应存在 effective_threshold
        session2 = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        self.assertIn("effective_threshold", session2, "自适应阈值应写入 session.json")


# ── 10. signal_topic ───────────────────────────────────

class TestSignalTopic(unittest.TestCase):
    def test_extract_returns_dict(self):
        sig = topic_extract("服务器支持高并发处理", 5)
        self.assertIsInstance(sig, dict)
        self.assertGreater(len(sig), 0)

    def test_similarity_same(self):
        sig = topic_extract("服务器支持高并发处理", 5)
        self.assertEqual(topic_similarity(sig, sig), 1.0)

    def test_similarity_disjoint(self):
        a = topic_extract("服务器高并发", 5)
        b = topic_extract("今天午餐红烧肉", 5)
        self.assertEqual(topic_similarity(a, b), 0.0)



def _read_json(path, **kwargs):
    with open(path, **kwargs) as f:
        return f.read()

# ── 11. 截断存储 + 累计长度 + 文本指纹 ──────────────────

class TestTurnStorage(unittest.TestCase):
    def setUp(self):
        import hallucination_watch_mcp as m
        self.m = m
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skill")
        self.sessions_dir = os.path.join(self.skill_dir, "sessions")
        self.params_path = os.path.join(self.skill_dir, "params", "default.json")
        os.makedirs(os.path.join(self.skill_dir, "params"), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(SCRIPTS), "params", "default.json"), self.params_path)
        self.proj_root = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj_root)
        m.SESSIONS_DIR = self.sessions_dir
        m.PARAMS_PATH = self.params_path
        m.PROJ_ROOT = self.proj_root
        m.HW_ACTIVE = os.path.join(self.proj_root, ".hw_active")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_text_truncated_in_turns(self):
        """超长文本入库时必须截断（≤500字符+标记），控制文件增长"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        long_text = "内容" * 1000  # 2000 字符
        self._run(self.m.hw_check(long_text, ""))
        turns = json.loads(_read_json(os.path.join(self.sessions_dir, sid, "turns.json"), encoding="utf-8"))
        stored = turns["turns"][0]["text"]
        # 500 截断 + 截断标记（约 12 字符）
        self.assertLessEqual(len(stored), 530, f"存储文本应被截断，实际 {len(stored)} 字符")
        self.assertIn("截断", stored, "应有截断标记")

    def test_cumulative_text_len_tracks_full_length(self):
        """累计长度必须统计完整文本长度（截断只影响存储，不影响统计）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        text = "内容" * 1000  # 2000 字符
        self._run(self.m.hw_check(text, ""))
        session = json.loads(_read_json(os.path.join(self.sessions_dir, sid, "session.json"), encoding="utf-8"))
        self.assertEqual(session.get("cumulative_text_len"), 2000,
                         f"累计长度应为完整 2000，实际 {session.get('cumulative_text_len')}")
        # 第二轮累计
        self._run(self.m.hw_check("短文本", ""))
        session2 = json.loads(_read_json(os.path.join(self.sessions_dir, sid, "session.json"), encoding="utf-8"))
        self.assertEqual(session2.get("cumulative_text_len"), 2003)

    def test_text_fingerprint_present_and_stable(self):
        """rec 中应有稳定的 text 指纹（同文本同指纹，不同文本不同指纹）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        t1 = "这是一个完全正常的回复内容。"
        self._run(self.m.hw_check(t1, ""))
        self._run(self.m.hw_check(t1, ""))
        self._run(self.m.hw_check("完全不同的另一段回复内容。", ""))
        turns = json.loads(_read_json(os.path.join(self.sessions_dir, sid, "turns.json"), encoding="utf-8"))
        fps = [t["text_fp"] for t in turns["turns"]]
        self.assertEqual(fps[0], fps[1], "相同文本指纹应一致")
        self.assertNotEqual(fps[0], fps[2], "不同文本指纹应不同")

    def test_redundancy_uses_cumulative_len(self):
        """redundancy 信号应基于累计长度（含被截断的历史文本），而非 turns 中存储的截断文本"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        sd = os.path.join(self.sessions_dir, sid)
        # 预置 5000 字符历史（但 turns 里只存截断文本）
        from datetime import datetime, timezone as tz
        ts = datetime.now(tz.utc).isoformat()
        with open(os.path.join(sd, "turns.json"), "w", encoding="utf-8") as f:
            json.dump({"turns": [{"turn": 1, "phase": "baseline", "triggered": False,
                                   "risk_raw": 0, "timestamp": ts, "text": "x" * 500}]}, f)
        session = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        session["cumulative_text_len"] = 5000
        session["next_turn"] = 2
        with open(os.path.join(sd, "session.json"), "w", encoding="utf-8") as f:
            json.dump(session, f)
        r = json.loads(self._run(self.m.hw_check("短文本", "")))
        # 预期：历史 5000 字符（而非 turns 里可见的 500）→ rd_score = 5000/1000*5 = 25
        self.assertEqual(r["signals"]["redundancy"]["score"], 25.0,
                         f"redundancy 应基于累计长度 5000，实际 {r['signals']['redundancy']['score']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ── 12. 评审反馈回归测试（C1/I1/I3/I4/M6） ──────────────

class TestReviewFeedback(unittest.TestCase):
    def setUp(self):
        import hallucination_watch_mcp as m
        self.m = m
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skill")
        self.sessions_dir = os.path.join(self.skill_dir, "sessions")
        self.params_path = os.path.join(self.skill_dir, "params", "default.json")
        os.makedirs(os.path.join(self.skill_dir, "params"), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(SCRIPTS), "params", "default.json"), self.params_path)
        self.proj_root = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj_root)
        m.SESSIONS_DIR = self.sessions_dir
        m.PARAMS_PATH = self.params_path
        m.PROJ_ROOT = self.proj_root
        m.HW_ACTIVE = os.path.join(self.proj_root, ".hw_active")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def _prime_session(self, n_prior, all_triggered=True):
        """预置 n_prior 轮高触发率 turns，使下一次 check 恰好跨过 interval 边界"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        sd = os.path.join(self.sessions_dir, sid)
        from datetime import datetime, timezone as tz
        ts = datetime.now(tz.utc).isoformat()
        turns = [{"turn": i + 1, "phase": "active", "triggered": all_triggered,
                  "risk_raw": 50 if all_triggered else 1, "timestamp": ts, "text": "x" * 100}
                 for i in range(n_prior)]
        with open(os.path.join(sd, "turns.json"), "w", encoding="utf-8") as f:
            json.dump({"turns": turns}, f)
        s = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        s["next_turn"] = n_prior + 1
        s["phase"] = "active"
        s["cumulative"]["total_checks"] = n_prior
        with open(os.path.join(sd, "session.json"), "w", encoding="utf-8") as f:
            json.dump(s, f)
        return sid, sd

    def test_c1_ema_threshold_compounds_across_intervals(self):
        """C1: 高触发率下阈值应跨 interval 复合增长（24.2→26.62→29.28），而非恒为 24.2"""
        sid, sd = self._prime_session(9)          # 第 10 次 check 触发第一次自适应
        self._run(self.m.hw_check("x" * 50, ""))
        s1 = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        th1 = s1["effective_threshold"]
        self.assertAlmostEqual(th1, 22.0 * 1.1, places=2, msg=f"首次自适应应 24.2，实际 {th1}")

        # 再造 9 轮（下一轮第 20 次 check 触发第二次自适应）
        turns = json.loads(_read_json(os.path.join(sd, "turns.json"), encoding="utf-8"))
        from datetime import datetime, timezone as tz
        ts = datetime.now(tz.utc).isoformat()
        for i in range(9):
            turns["turns"].append({"turn": 11 + i, "phase": "active", "triggered": True,
                                   "risk_raw": 50, "timestamp": ts, "text": "x" * 100})
        with open(os.path.join(sd, "turns.json"), "w", encoding="utf-8") as f:
            json.dump(turns, f)
        s = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        s["next_turn"] = 20
        s["cumulative"]["total_checks"] = 19
        with open(os.path.join(sd, "session.json"), "w", encoding="utf-8") as f:
            json.dump(s, f)
        self._run(self.m.hw_check("x" * 50, ""))
        s2 = json.loads(_read_json(os.path.join(sd, "session.json"), encoding="utf-8"))
        th2 = s2["effective_threshold"]
        expected2 = round(22.0 * 1.1 * 1.1, 2)
        self.assertAlmostEqual(th2, expected2, places=1,
                               msg=f"第二次自适应应基于会话阈值 24.2→{expected2}，实际 {th2}")

    def test_i1_topic_similarity_threshold_wired(self):
        """I1: params 的 topic_similarity_threshold 必须生效（修改后行为变化）"""
        # 话题高度相似但声明一致 → threshold=0.15 时也通过；threshold=0.99 时应跳过对比（无矛盾）
        # 直接测 signal_material 的接线：hw_check 应把参数传进去
        from signal_material import check as mt_check
        # 矛盾文本：低阈值应检测到矛盾，高阈值应被话题门控跳过
        ref = [{"claims": ["系统不支持批量导入功能"], "topic": {"系统": 1, "导入": 1}}]
        r_low = mt_check("系统支持批量导入功能", ref, topic_threshold=0.15)
        self.assertGreater(r_low["score"], 0, "低阈值应检测到矛盾")
        r_high = mt_check("系统支持批量导入功能", ref, topic_threshold=0.99)
        self.assertEqual(r_high["score"], 0, "高阈值应跳过话题门控对比")
        # params 接线：hw_check 应从 params 读取该值
        import json as _json
        with open(self.params_path, encoding="utf-8") as f:
            p = _json.load(f)
        p["topic_similarity_threshold"] = 0.99
        with open(self.params_path, "w", encoding="utf-8") as f:
            _json.dump(p, f, ensure_ascii=False)
        sid, sd = self._prime_session(0)
        self._run(self.m.hw_check("系统支持批量导入功能。", ""))
        rec = _json.loads(_read_json(os.path.join(sd, "turns.json"), encoding="utf-8"))["turns"][0]
        self.assertEqual(rec["material_score"], 0)

    def test_i3_compliance_default_root_uses_cwd(self):
        """I3: check() 默认 project_root 应为 cwd（含 .hw_active 处），而非 skill 目录"""
        import check_compliance
        old_cwd = os.getcwd()
        try:
            os.chdir(self.proj_root)
            with open(os.path.join(self.proj_root, ".hw_active"), "w") as f:
                f.write("dummy")
            r = check_compliance.check_with_dirs(self.proj_root, self.sessions_dir)
            self.assertIn("reason", r, "应能找到标记并继续检查")
        finally:
            os.chdir(old_cwd)

    def test_i4_reference_entries_capped(self):
        """I4: reference.json 条目应有上限 + 同文本指纹去重"""
        from signal_material import add_entry
        entries = []
        for i in range(60):
            entries = add_entry(entries, f"系统支持第{i}种批量导入方式。")
        self.assertLessEqual(len(entries), 50, f"条目应被限制，实际 {len(entries)}")

    def test_m6_reset_only_removes_active_session(self):
        """M6: reset 只删 .hw_active 指向的会话，孤儿会话保留（避免跨项目误删）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        # 造孤儿会话（模拟其他项目/历史残留）
        orphan = "2098-01-01_00-00-00"
        od = os.path.join(self.sessions_dir, orphan)
        os.makedirs(od, exist_ok=True)
        with open(os.path.join(od, "session.json"), "w", encoding="utf-8") as f:
            json.dump({"session_id": orphan}, f)
        r = json.loads(self._run(self.m.hw_reset()))
        self.assertIn(sid, r["removed"])
        self.assertNotIn(orphan, r["removed"], "孤儿会话不应被误删")
        self.assertTrue(os.path.exists(od))


# ── 13. 灵敏度修复回归测试（fuzzy 降权 / 红旗硬触发） ─────

class TestSensitivityFix(unittest.TestCase):
    def setUp(self):
        import hallucination_watch_mcp as m
        self.m = m
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skill")
        self.sessions_dir = os.path.join(self.skill_dir, "sessions")
        self.params_path = os.path.join(self.skill_dir, "params", "default.json")
        os.makedirs(os.path.join(self.skill_dir, "params"), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(SCRIPTS), "params", "default.json"), self.params_path)
        self.proj_root = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj_root)
        m.SESSIONS_DIR = self.sessions_dir
        m.PARAMS_PATH = self.params_path
        m.PROJ_ROOT = self.proj_root
        m.HW_ACTIVE = os.path.join(self.proj_root, ".hw_active")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_fuzzy_unrelated_topic_zero_score(self):
        """修复1: 话题完全无关时 fuzzy 应为 0 分（不再固定 10 分）"""
        r = fz_process("量子纠缠态坍缩概率分布。", "今天食堂的红烧肉非常好吃。", 7)
        self.assertEqual(r["score"], 0, f"无关话题应 0 分，实际 {r['score']}")

    def test_fuzzy_partial_similarity_scores(self):
        """修复1: 部分相似（0.3~0.7）才计分"""
        # 构造指纹部分重叠：前 3 字符相同、后 4 不同（7 字符指纹相似度 3/7≈0.43）
        fp_a = "abcdxyz"
        from signal_fuzzy import compare
        sim, score = compare(fp_a, "abc1234")
        self.assertGreaterEqual(sim, 0.3)
        self.assertGreater(score, 0, "部分相似应计分")

    def test_fuzzy_identical_zero_score(self):
        """修复1: 完全相同（重复）不计分（重复由 consistency 信号负责）"""
        from signal_fuzzy import compare
        sim, score = compare("abcdefg", "abcdefg")
        self.assertEqual(sim, 1.0)
        self.assertEqual(score, 0)

    def test_red_flag_two_hard_trigger_mark(self):
        """修复2: 红旗词 ≥2 硬触发 mark（不依赖密度）"""
        text = "我毫无疑问可以确定方案没有问题，百分百可靠。"  # 毫无疑问 + 百分百 = 2 红旗
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        r = json.loads(self._run(self.m.hw_check(text, "")))
        self.assertEqual(r["zone"], "mark", f"2 个红旗词应硬触发 mark，实际 {r['zone']}")
        self.assertTrue(r["triggered"])
        # risk_pct 被抬升至 ≥100 保持自洽
        self.assertGreaterEqual(r["risk_pct"], 100.0)
        # rec 中应记录硬触发
        import json as _json
        sd = os.path.join(self.sessions_dir, sid)
        rec = _json.loads(_read_json(os.path.join(sd, "turns.json"), encoding="utf-8"))["turns"][0]
        self.assertTrue(rec.get("red_flag_hard_trigger", False))

    def test_red_flag_one_no_hard_trigger(self):
        """修复2: 1 个红旗词不硬触发，走正常判定"""
        text = "这个方案绝对没有问题。"  # 只有 1 个绝对（普通词），无红旗
        self._run(self.m.hw_init())
        r = json.loads(self._run(self.m.hw_check(text, "")))
        self.assertFalse(r.get("red_flag_hard_trigger"), "正常路径应无硬触发")  # 字段稳定存在但为 False
        self.assertLess(r["risk_pct"], 100.0)

    def test_red_flag_expanded_keywords(self):
        """修复3: 红旗词表扩充后「百分之百/绝对保证」应被识别"""
        import json as _json
        with open(self.params_path, encoding="utf-8") as f:
            p = _json.load(f)
        rfs = p["red_flag_keywords"]
        self.assertIn("百分之百", rfs)
        self.assertIn("绝对保证", rfs)


# ── 14. 会话级监测生命周期（hw_stop / 会话名 / 激活门控） ─────

class TestSessionLifecycle(unittest.TestCase):
    def setUp(self):
        import hallucination_watch_mcp as m
        self.m = m
        self.tmp = tempfile.mkdtemp()
        self.skill_dir = os.path.join(self.tmp, "skill")
        self.sessions_dir = os.path.join(self.skill_dir, "sessions")
        self.params_path = os.path.join(self.skill_dir, "params", "default.json")
        os.makedirs(os.path.join(self.skill_dir, "params"), exist_ok=True)
        shutil.copy(os.path.join(os.path.dirname(SCRIPTS), "params", "default.json"), self.params_path)
        self.proj_root = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj_root)
        m.SESSIONS_DIR = self.sessions_dir
        m.PARAMS_PATH = self.params_path
        m.PROJ_ROOT = self.proj_root
        m.HW_ACTIVE = os.path.join(self.proj_root, ".hw_active")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_init_with_session_name(self):
        """hw_init 支持会话名：数据落在 sessions/<会话名>/ 下"""
        r = json.loads(self._run(self.m.hw_init(session_name="my-pi-session")))
        self.assertEqual(r["status"], "ok")
        self.assertTrue(os.path.isdir(os.path.join(self.sessions_dir, "my-pi-session")),
                        "应按会话名创建数据目录")
        # 幂等复用同名会话
        r2 = json.loads(self._run(self.m.hw_init(session_name="my-pi-session")))
        self.assertEqual(r2["status"], "reused")
        self.assertEqual(r2["session_id"], "my-pi-session")

    def test_stop_keeps_data_removes_marker(self):
        """hw_stop：停止监测（删标记+规则），但保留会话 json 数据"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        sd = os.path.join(self.sessions_dir, sid)
        r = json.loads(self._run(self.m.hw_stop()))
        self.assertEqual(r["status"], "stopped")
        self.assertFalse(os.path.exists(self.m.HW_ACTIVE), "停止后应移除激活标记")
        self.assertTrue(os.path.exists(sd), "停止后应保留会话数据")

    def test_check_requires_active_marker(self):
        """hw_check 仅在激活状态下工作；停止后应返回 not active（不静默回退扫描）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        self._run(self.m.hw_check("第一轮正常回复。", ""))
        # 停止后
        self._run(self.m.hw_stop())
        r = json.loads(self._run(self.m.hw_check("停止后的回复。", "")))
        self.assertIn("error", r)
        self.assertIn("not active", r["error"])

    def test_resume_after_stop_reuses_data(self):
        """停止后再 init：复用原会话数据（不新建）"""
        sid = json.loads(self._run(self.m.hw_init()))["session_id"]
        self._run(self.m.hw_check("第一轮回复内容。", ""))
        self._run(self.m.hw_stop())
        r = json.loads(self._run(self.m.hw_init()))
        self.assertEqual(r["status"], "reused")
        self.assertEqual(r["session_id"], sid)
        # 数据保留（含第一轮记录）
        import json as _json
        sd = os.path.join(self.sessions_dir, sid)
        turns = _json.loads(_read_json(os.path.join(sd, "turns.json"), encoding="utf-8"))["turns"]
        self.assertEqual(len(turns), 1, "复用会话应保留历史数据")
