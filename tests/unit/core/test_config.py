from src.core import config


class TestConfigValues:
    def test_chrome_user_data_default(self):
        assert hasattr(config, 'CHROME_USER_DATA')
        assert isinstance(config.CHROME_USER_DATA, str)

    def test_chrome_executable_path_default(self):
        assert hasattr(config, 'CHROME_EXECUTABLE_PATH')
        assert isinstance(config.CHROME_EXECUTABLE_PATH, str)

    def test_chrome_user_data_from_env(self, monkeypatch):
        monkeypatch.setenv("CHROME_USER_DATA", "/custom/path")
        import importlib
        importlib.reload(config)
        assert config.CHROME_USER_DATA == "/custom/path"

    def test_chrome_executable_path_from_env(self, monkeypatch):
        monkeypatch.setenv("CHROME_EXECUTABLE_PATH", "/custom/chrome")
        import importlib
        importlib.reload(config)
        assert config.CHROME_EXECUTABLE_PATH == "/custom/chrome"
