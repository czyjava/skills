#!/usr/bin/env python3
"""验证 Modulith 与 Javadoc 静态审计脚本。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_java_modulith.py"


class AuditJavaModulithTest(unittest.TestCase):
    """覆盖无问题工程和典型违规工程。"""

    def setUp(self) -> None:
        """为每个用例创建隔离的临时工程。"""

        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        """删除用例生成的临时工程。"""

        self._temporary_directory.cleanup()

    def _write(self, relative: str, content: str) -> None:
        """写入去除公共缩进的 Java 测试夹具。"""

        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    def _run(self) -> dict[str, object]:
        """以 JSON 模式运行脚本并返回报告。"""

        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(self.root),
                "--base-package",
                "cn.mucang.demo",
                "--format",
                "json",
                "--fail-on",
                "never",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(process.stdout)

    def _write_structure_entry_and_test(self) -> None:
        """写入所有测试场景共用的结构入口和结构测试。"""

        self._write(
            "app/src/main/java/cn/mucang/demo/DemoModulith.java",
            """
            package cn.mucang.demo;

            /**
             * 演示工程结构入口。
             */
            @Modulithic(systemName = "demo")
            public final class DemoModulith {
            }
            """,
        )
        self._write(
            "app/src/test/java/cn/mucang/demo/ApplicationModulesTest.java",
            """
            package cn.mucang.demo;

            class ApplicationModulesTest {
                @Test
                void verifyApplicationModuleBoundaries() {
                    ApplicationModules.of(DemoModulith.class).verify();
                }
            }
            """,
        )

    def test_clean_project_has_no_findings(self) -> None:
        """完整 Javadoc 和合法公开面不应产生审计结果。"""

        self._write_structure_entry_and_test()
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/package-info.java",
            """
            /**
             * 报名领域，负责创建和维护报名申请。
             */
            @ApplicationModule(displayName = "报名")
            package cn.mucang.demo.enrollment;
            """,
        )
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/EnrollmentApi.java",
            """
            package cn.mucang.demo.enrollment;

            /**
             * 报名领域公开能力。
             */
            public interface EnrollmentApi {
                /**
                 * 创建报名申请。
                 *
                 * @param command 已确认的报名意图
                 * @return 报名处理结果
                 */
                EnrollmentResult enroll(EnrollmentCommand command);
            }
            """,
        )
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/EnrollmentCommand.java",
            """
            package cn.mucang.demo.enrollment;

            /**
             * 报名命令。
             */
            public final class EnrollmentCommand {
                /** 学员 ID，标识待报名学员。 */
                private long studentId;
            }
            """,
        )
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/EnrollmentResult.java",
            """
            package cn.mucang.demo.enrollment;

            /**
             * 报名结果。
             */
            public final class EnrollmentResult {
                /** 报名申请 ID，标识本次创建的申请。 */
                private long enrollmentId;
            }
            """,
        )

        report = self._run()

        self.assertEqual([], report["findings"])

    def test_missing_docs_and_internal_import_are_reported(self) -> None:
        """同时报告 Javadoc 缺口和跨域内部包访问。"""

        self._write_structure_entry_and_test()
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/package-info.java",
            """
            @ApplicationModule(displayName = "报名")
            package cn.mucang.demo.enrollment;
            """,
        )
        self._write(
            "app/src/main/java/cn/mucang/demo/payment/package-info.java",
            """
            /** 支付领域。 */
            @ApplicationModule(displayName = "支付")
            package cn.mucang.demo.payment;
            """,
        )
        self._write(
            "app/src/main/java/cn/mucang/demo/enrollment/EnrollmentCommand.java",
            """
            package cn.mucang.demo.enrollment;

            import cn.mucang.demo.payment.infrastructure.PaymentDao;

            public final class EnrollmentCommand {
                private long studentId;

                public EnrollmentCommand(long studentId) {
                    this.studentId = studentId;
                }

                /**
                 * 描述报名目标。
                 */
                public String describe(long schoolId) throws IllegalStateException {
                    return String.valueOf(schoolId);
                }

                public void undocumented() {
                }
            }
            """,
        )

        report = self._run()
        codes = {item["code"] for item in report["findings"]}

        self.assertTrue(
            {"ARCH003", "DOC001", "DOC002", "DOC003", "DOC004", "DOC005", "DOC006", "DOC007"}.issubset(codes),
            report,
        )


if __name__ == "__main__":
    unittest.main()
