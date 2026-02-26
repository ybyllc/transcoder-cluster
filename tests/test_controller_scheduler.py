"""Controller 调度器测试。"""

from pathlib import Path

from transcoder_cluster.core.controller import Controller


class TestControllerScheduler:
    """批量调度相关测试。"""

    def test_build_output_path_with_conflict(self, tmp_path: Path):
        """输出命名冲突时应自动追加编号。"""
        input_file = tmp_path / "sample.mp4"
        input_file.write_bytes(b"dummy")

        first_output = tmp_path / "sample_transcoded.mp4"
        first_output.write_bytes(b"existing")

        controller = Controller()
        output = controller.build_output_path(str(input_file))
        assert output.endswith("sample_transcoded_2.mp4")

    def test_validate_output_file(self, tmp_path: Path):
        """输出文件校验：不存在/空文件/有效文件。"""
        controller = Controller()

        missing_path = tmp_path / "missing.mp4"
        ok, message = controller._validate_output_file(str(missing_path))
        assert ok is False
        assert "不存在" in message

        empty_path = tmp_path / "empty.mp4"
        empty_path.write_bytes(b"")
        ok, message = controller._validate_output_file(str(empty_path))
        assert ok is False
        assert "大小为 0" in message

        valid_path = tmp_path / "valid.mp4"
        valid_path.write_bytes(b"not-empty")
        ok, message = controller._validate_output_file(str(valid_path))
        assert ok is True
        assert message == ""

    def test_dispatch_retry_once_then_success(self):
        """失败后应按 max_attempts 重试并成功。"""
        controller = Controller()
        task = controller.create_task("input.mp4", "output.mp4", ["-c:v", "libx265"], max_attempts=2)

        call_count = {"value": 0}

        def fake_submit(*args, **kwargs):
            call_count["value"] += 1
            if call_count["value"] == 1:
                return False, "first failed"
            return True, None

        controller._submit_with_progress = fake_submit

        result = controller.dispatch_tasks([task], ["192.168.1.2"])
        assert result["completed"] == 1
        assert result["failed"] == 0
        assert task.status == "completed"
        assert task.attempts == 2

    def test_dispatch_retry_exhausted(self):
        """超过重试次数后应标记失败。"""
        controller = Controller()
        task = controller.create_task("input.mp4", "output.mp4", ["-c:v", "libx265"], max_attempts=2)

        def always_fail(*args, **kwargs):
            return False, "always failed"

        controller._submit_with_progress = always_fail

        result = controller.dispatch_tasks([task], ["192.168.1.2"])
        assert result["completed"] == 0
        assert result["failed"] == 1
        assert task.status == "failed"
        assert task.attempts == 2
