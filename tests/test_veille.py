import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import veille  # noqa: E402


def item(url, compte, likes, comments=0, type_="Image", **extra):
    return {
        "url": url,
        "ownerUsername": compte,
        "likesCount": likes,
        "commentsCount": comments,
        "type": type_,
        "caption": f"Accroche de {url}\nsuite du texte",
        "timestamp": "2026-10-30T10:00:00.000Z",
        "hashtags": ["psychologie"],
        **extra,
    }


@pytest.mark.parametrize(
    "entree,attendu",
    [
        ("@Psy.Compte", "psy.compte"),
        ("psy_compte", "psy_compte"),
        ("https://www.instagram.com/psy_compte/", "psy_compte"),
        ("instagram.com/psy_compte?igsh=abc", "psy_compte"),
    ],
)
def test_normaliser_compte(entree, attendu):
    assert veille.normaliser_compte(entree) == attendu


def test_lien_de_publication_refuse():
    with pytest.raises(ValueError, match="публикацию"):
        veille.normaliser_compte("https://www.instagram.com/reel/ABC123/")


def test_config_et_urls(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("comptes: ['@a', a, b]\nhashtags: ['#Psychologie']\n", encoding="utf-8")
    cfg = veille.charger_config(f)
    assert cfg.comptes == ["a", "b"]
    assert veille.urls_sources(cfg)[-1] == "https://www.instagram.com/explore/tags/psychologie/"


def test_config_vide_refusee(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("comptes:\nhashtags:\n", encoding="utf-8")
    with pytest.raises(ValueError):
        veille.charger_config(f)


def test_analyse_detecte_surperformance():
    items = [
        item("u1", "psy", 100),
        item("u2", "psy", 110),
        item("u3", "psy", 90),
        item("u4", "psy", 1000, 50, type_="Video", productType="clips", videoPlayCount=20000),
        item("u5", "autre", -1, 3),  # likes masqués
        {"url": "u6", "error": "not found"},
        item("u1", "psy", 100),  # doublon
    ]
    pubs = veille.convertir(items)
    assert len(pubs) == 5
    a = veille.analyser(pubs, top_n=3)
    assert a.surperformances[0].url == "u4"
    assert a.surperformances[0].format == "Reels"
    assert a.surperformances[0].ratio == pytest.approx(1050 / 105)
    assert "u4" not in {p.url for p in a.top}
    assert a.formats[0][0] == "Reels"


def test_rapport_echappe_html_et_respecte_limite():
    items = [item(f"u{i}", "psy", 10 * i, caption="<b>&" + "x" * 500) for i in range(1, 60)]
    for it in items:
        it["caption"] = "<script> & " + "x" * 500
    pubs = veille.convertir(items)
    cfg = veille.Config(comptes=["psy"], hashtags=[], top_n=40)
    msgs = veille.construire_rapport(veille.analyser(pubs, cfg.top_n), cfg)
    assert len(msgs) > 1
    assert all(len(m) <= veille.LIMITE_MESSAGE_TELEGRAM for m in msgs)
    assert "<script>" not in "".join(msgs)


def test_main_avec_fichier(tmp_path, capsys):
    import json

    cfg = tmp_path / "c.yaml"
    cfg.write_text("comptes: [psy]\n", encoding="utf-8")
    data = tmp_path / "d.json"
    data.write_text(json.dumps([item("u1", "psy", 5)]), encoding="utf-8")
    code = veille.main(
        ["--config", str(cfg), "--fichier", str(data), "--dry-run", "--sorties", str(tmp_path / "s")]
    )
    assert code == 0
    assert "Мониторинг Instagram" in capsys.readouterr().out
    assert list((tmp_path / "s").glob("*.csv"))


def test_messages_ia_echappes_et_coupes():
    texte = "Раздел <1> & тест\n\n" + "\n".join("строка " + "я" * 80 for _ in range(120))
    msgs = veille.messages_analyse_ia(texte)
    assert msgs[0].startswith("🧠 <b>Разбор от ИИ</b>")
    assert "&lt;1&gt; &amp;" in msgs[0]
    assert len(msgs) > 1 and all(len(m) <= veille.LIMITE_MESSAGE_TELEGRAM for m in msgs)


def test_ia_sautee_sans_cle(monkeypatch):
    import analyse_ia

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pubs = veille.convertir([item("u1", "psy", 5)])
    assert analyse_ia.analyser_avec_ia(pubs) is None


def test_ia_appel_et_prompt(monkeypatch):
    import types

    import anthropic

    import analyse_ia

    capture = {}

    class FauxMessages:
        def create(self, **kw):
            capture.update(kw)
            return types.SimpleNamespace(
                stop_reason="end_turn",
                content=[types.SimpleNamespace(type="text", text="Разбор")],
                usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    class FauxClient:
        def __init__(self, *a, **k):
            self.beta = types.SimpleNamespace(messages=FauxMessages())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(anthropic, "Anthropic", FauxClient)
    pubs = veille.convertir([item("u1", "psy", 5, caption="Хук недели")])
    assert analyse_ia.analyser_avec_ia(pubs) == "Разбор"
    assert capture["model"] == "claude-opus-5-5"
    assert "Хук недели" in capture["messages"][0]["content"]
