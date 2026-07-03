import pytest

from server.config import ConfigError, load_config


def write_env(tmp_path, content):
    (tmp_path / ".env").write_text(content, encoding="utf-8")


def test_loads_api_key_from_env_file(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=RGAPI-test-key\nACCOUNTS=Foo#BAR\n")
    cfg = load_config(tmp_path)
    assert cfg.riot_api_key == "RGAPI-test-key"


def test_env_parser_ignores_comments_blanks_and_strips_quotes(tmp_path):
    write_env(tmp_path, "# comment\n\nRIOT_API_KEY=\"RGAPI-quoted\"\nACCOUNTS=Foo#BAR\nOTHER=x\n")
    cfg = load_config(tmp_path)
    assert cfg.riot_api_key == "RGAPI-quoted"


def test_accounts_parsed_from_env_file(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=k\nACCOUNTS=Foo#BAR, Baz#EUW\n")
    cfg = load_config(tmp_path)
    assert cfg.accounts == [("Foo", "BAR"), ("Baz", "EUW")]


def test_any_number_of_accounts(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=k\nACCOUNTS=A#EUW,B#EUW,C#NA1,D#KR\n")
    cfg = load_config(tmp_path)
    assert len(cfg.accounts) == 4
    assert cfg.accounts[3] == ("D", "KR")


def test_missing_accounts_raises_config_error(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=k\n")
    with pytest.raises(ConfigError, match="ACCOUNTS"):
        load_config(tmp_path)


def test_account_names_with_spaces_and_unicode(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=k\nACCOUNTS=Ünï côdé#EUW\n")
    cfg = load_config(tmp_path)
    assert cfg.accounts == [("Ünï côdé", "EUW")]


def test_db_path_defaults_under_root_data_dir(tmp_path):
    write_env(tmp_path, "RIOT_API_KEY=k\nACCOUNTS=Foo#BAR\n")
    cfg = load_config(tmp_path)
    assert cfg.db_path == tmp_path / "data" / "lol.sqlite"


def test_missing_key_raises_config_error(tmp_path):
    write_env(tmp_path, "OTHER=x\n")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_missing_env_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path)
