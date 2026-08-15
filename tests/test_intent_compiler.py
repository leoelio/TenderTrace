from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

from tendertrace.intent import compile_intent
from tendertrace.intent.schedule import extract_time_of_day
from tendertrace.intent.time_expr import parse_time_expr, resolve_window


NOW = datetime(2026, 7, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class IntentCompilerTests(unittest.TestCase):
    def test_competition_example_immediate_relative_month(self) -> None:
        bidql = compile_intent("最近1个月的安徽省区域内的服务器招标信息都有哪些", now=NOW)
        self.assertEqual(bidql["topic"]["core"], ["服务器"])
        self.assertEqual(bidql["region"]["province"], "安徽")
        self.assertEqual(bidql["region"]["adcode"], "340000")
        self.assertEqual(bidql["time"]["kind"], "relative")
        self.assertEqual(bidql["time"]["ast"], {"op": "last", "unit": "month", "n": 1})
        self.assertEqual(bidql["schedule"]["kind"], "immediate")
        self.assertEqual(bidql["time"]["resolved_window"], {"from": "2026-06-06", "to": "2026-07-06"})

    def test_competition_example_absolute_month(self) -> None:
        bidql = compile_intent("2026年3月份的上海区域内的充电桩招标信息都有哪些")
        self.assertEqual(bidql["topic"]["core"], ["充电桩"])
        self.assertEqual(bidql["region"]["province"], "上海")
        self.assertEqual(bidql["time"]["kind"], "absolute")
        self.assertEqual(bidql["time"]["from"], "2026-03-01")
        self.assertEqual(bidql["time"]["to"], "2026-03-31")
        self.assertEqual(bidql["schedule"]["kind"], "immediate")

    def test_competition_example_daily_recurring(self) -> None:
        bidql = compile_intent("最近3个月的上海区域内的充电桩招标信息都有哪些，请汇总后每天9:00发送给我")
        self.assertEqual(bidql["topic"]["core"], ["充电桩"])
        self.assertEqual(bidql["time"]["ast"], {"op": "last", "unit": "month", "n": 3})
        self.assertEqual(bidql["schedule"]["kind"], "recurring")
        self.assertEqual(bidql["schedule"]["cron"], "0 9 * * *")

    def test_competition_example_today_once_at(self) -> None:
        bidql = compile_intent("2026年4月份上海的充电桩招标信息都有哪些，请汇总后今天9:00发送给我")
        self.assertEqual(bidql["topic"]["core"], ["充电桩"])
        self.assertEqual(bidql["time"]["from"], "2026-04-01")
        self.assertEqual(bidql["time"]["to"], "2026-04-30")
        self.assertEqual(bidql["schedule"]["kind"], "once_at")
        self.assertEqual(bidql["schedule"]["time"], "09:00")

    def test_weekly_chinese_time_and_default_window(self) -> None:
        bidql = compile_intent("帮我盯着河南的储能项目，每周一早上八点半来一份")
        self.assertEqual(bidql["topic"]["core"], ["储能"])
        self.assertEqual(bidql["region"]["province"], "河南")
        self.assertEqual(bidql["time"]["kind"], "relative")
        self.assertEqual(bidql["time"]["origin"], "default")
        self.assertEqual(bidql["schedule"]["kind"], "recurring")
        self.assertEqual(bidql["schedule"]["cron"], "30 8 * * 1")

    def test_nationwide_scope_is_not_topic_keyword(self) -> None:
        bidql = compile_intent("最近10天全国设备招标信息都有哪些", now=NOW)

        self.assertEqual(bidql["topic"]["core"], ["设备"])
        self.assertIsNone(bidql["region"]["province"])

    def test_city_scope_and_multiple_topics_are_parsed(self) -> None:
        bidql = compile_intent("最近36个月杭州市的空调或者服务器投标信息都有哪些", now=NOW)

        self.assertEqual(bidql["region"]["province"], "浙江")
        self.assertEqual(bidql["region"]["city"], "杭州")
        self.assertEqual(bidql["region"]["adcode"], "330000")
        self.assertEqual(bidql["region"]["city_adcode"], "330100")
        self.assertEqual(bidql["topic"]["core"], ["空调", "服务器"])
        self.assertNotIn("region", bidql["meta"]["clarify_needed"])

    def test_complete_city_dictionary_parses_suzhou_and_chengdu(self) -> None:
        suzhou = compile_intent("最近1个月苏州市充电桩招标信息都有哪些", now=NOW)
        chengdu = compile_intent("最近1个月成都服务器招标信息都有哪些", now=NOW)

        self.assertEqual(suzhou["region"]["province"], "江苏")
        self.assertEqual(suzhou["region"]["city"], "苏州")
        self.assertEqual(suzhou["region"]["city_adcode"], "320500")
        self.assertEqual(chengdu["region"]["province"], "四川")
        self.assertEqual(chengdu["region"]["city"], "成都")
        self.assertEqual(chengdu["region"]["city_adcode"], "510100")

    def test_category_dictionary_normalizes_topic_synonym(self) -> None:
        bidql = compile_intent("最近1个月上海充电设施招标信息都有哪些", now=NOW)

        self.assertEqual(bidql["topic"]["core"], ["充电桩"])
        expanded = [item["term"] for item in bidql["topic"]["expanded"]]
        self.assertIn("充电设施", expanded)
        self.assertGreaterEqual(bidql["meta"]["confidence"]["topic"], 0.9)

    def test_global_scope_enables_official_overseas_source_terms(self) -> None:
        bidql = compile_intent("最近1个月全球服务器招标信息", now=NOW)

        self.assertEqual(bidql["region"]["scope"], "global")
        self.assertIn("server", bidql["topic"]["source_terms"])
        self.assertNotIn("region", bidql["meta"]["clarify_needed"])

    def test_uk_scope_routes_to_uk_official_sources(self) -> None:
        bidql = compile_intent("最近1个月英国服务器采购信息", now=NOW)

        self.assertEqual(bidql["region"]["scope"], "uk")
        self.assertIn("server", bidql["topic"]["source_terms"])
        self.assertNotIn("region", bidql["meta"]["clarify_needed"])

    def test_low_confidence_topic_requests_clarification(self) -> None:
        bidql = compile_intent("最近1个月上海相关信息有哪些", now=NOW)

        self.assertIn("topic", bidql["meta"]["clarify_needed"])
        self.assertEqual(bidql["meta"]["clarification_questions"][0]["field"], "topic")

    def test_all_tender_query_can_leave_topic_open(self) -> None:
        bidql = compile_intent("最近36个月杭州市的全部投标信息都有哪些", now=NOW)

        self.assertEqual(bidql["region"]["city"], "杭州")
        self.assertEqual(bidql["topic"]["core"], [])

    def test_chinese_number_relative_window(self) -> None:
        parsed = parse_time_expr("最近三个月北京服务器招标信息")
        self.assertEqual(parsed.value["ast"], {"op": "last", "unit": "month", "n": 3})
        self.assertEqual(resolve_window(parsed.value, NOW), {"from": "2026-04-06", "to": "2026-07-06"})

    def test_extract_time_of_day(self) -> None:
        self.assertEqual(extract_time_of_day("每天9:30发送"), (9, 30, "9:30"))
        self.assertEqual(extract_time_of_day("每周一早上八点半来一份"), (8, 30, "八点半"))


if __name__ == "__main__":
    unittest.main()
