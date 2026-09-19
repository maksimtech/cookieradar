"""The consolidated ePrivacy directive: a different EUR-Lex layout from the GDPR."""
from pathlib import Path

import pytest

from cookieradar import law_fetcher
from cookieradar.law_fetcher import EPRIVACY, LawFetchError, fetch_provisions, parse_articles

PAGE = Path(__file__).parent / "fixtures" / "eprivacy_it_consolidated_excerpt.html"


@pytest.fixture(scope="module")
def texts():
    return parse_articles(PAGE.read_text(encoding="utf-8"), ("5",))


def test_consolidated_version_is_the_one_cited():
    # 32002L0058 is the 2002 original, where art. 5(3) only required the right
    # to refuse; the 2009 amendment requires prior consent
    assert EPRIVACY.celex == "02002L0058-20091219"
    assert EPRIVACY.name == "ePrivacy dir. 2002/58/CE"


def test_article_5_paragraphs(texts):
    assert set(texts) == {"5", "5(1)", "5(2)", "5(3)"}
    assert texts["5"] == "\n".join(texts[f"5({n})"] for n in (1, 2, 3))


def test_article_5_3_is_the_amended_text(texts):
    assert texts["5(3)"].startswith(
        "3. Gli Stati membri assicurano che l’archiviazione di informazioni oppure l’accesso "
        "a informazioni già archiviate nell’apparecchiatura terminale di un abbonato o di un "
        "utente sia consentito unicamente a condizione che l’abbonato o l’utente in questione "
        "abbia espresso preliminarmente il proprio consenso"
    )
    assert texts["5(3)"].endswith("esplicitamente richiesto dall’abbonato o dall’utente a erogare tale servizio.")


def test_amendment_markers_and_titles_are_dropped(texts):
    for text in texts.values():
        assert "▼" not in text and "►" not in text
        assert "Riservatezza delle comunicazioni" not in text
        assert "Articolo" not in text


def test_article_ends_before_the_next_one(texts):
    assert "Dati sul traffico" not in texts["5"]
    assert "I dati sul traffico" not in texts["5"]


def test_other_article_of_the_excerpt(texts):
    six = parse_articles(PAGE.read_text(encoding="utf-8"), ("6",))
    assert six["6(1)"].startswith("1. I dati sul traffico relativi agli abbonati")


def test_missing_article_raises():
    with pytest.raises(LawFetchError, match="99"):
        parse_articles(PAGE.read_text(encoding="utf-8"), ("99",))


def test_fetch_provisions_uses_the_consolidated_celex(monkeypatch):
    urls = []

    def fake_fetch_html(url, **kwargs):
        urls.append(url)
        return PAGE.read_text(encoding="utf-8")

    monkeypatch.setattr(law_fetcher, "fetch_html", fake_fetch_html)
    provisions = fetch_provisions(EPRIVACY, ("5",))

    assert urls == ["https://eur-lex.europa.eu/legal-content/IT/TXT/HTML/?uri=CELEX:02002L0058-20091219"]
    assert provisions["5(3)"].celex == "02002L0058-20091219"
    assert provisions["5(3)"].key == ("02002L0058-20091219", "5(3)")
