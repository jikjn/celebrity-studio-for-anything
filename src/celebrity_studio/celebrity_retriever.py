from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import quote

import requests

from .llm import LLMClient
from .models import CelebrityCandidate, ScenarioSpec


WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_SEARCH_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _safe_float(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class WikidataRetriever:
    timeout_s: int = 25
    user_agent: str = "MindForgeStudio/0.3 (contact: local-user)"

    def search_entities(self, query: str, limit: int = 12, language: str = "en") -> list[dict]:
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": language,
            "search": query,
            "type": "item",
            "limit": limit,
        }
        response = requests.get(
            WIKIDATA_API,
            params=params,
            timeout=self.timeout_s,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        return response.json().get("search", [])

    def get_entity_details(self, ids: list[str]) -> dict[str, dict]:
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(ids),
            "languages": "en|zh",
            "props": "labels|descriptions|claims|sitelinks",
        }
        response = requests.get(
            WIKIDATA_API,
            params=params,
            timeout=self.timeout_s,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        return response.json().get("entities", {})


def _parse_birth_year(claims: dict) -> int | None:
    try:
        p569 = claims.get("P569", [])
        if not p569:
            return None
        time_text = p569[0]["mainsnak"]["datavalue"]["value"]["time"]
        year = int(time_text[1:5])
        return year
    except Exception:
        return None


def _infer_era(year: int | None) -> str:
    if year is None:
        return "modern"
    if year < 1700:
        return "ancient"
    if year < 1950:
        return "modern"
    return "contemporary"


def _build_search_terms(spec: ScenarioSpec, llm: LLMClient | None) -> list[str]:
    fallback = [spec.raw_user_query]
    fallback.extend(f"{tag} influential person" for tag in spec.domain_tags[:6])
    fallback.extend(f"{tag} pioneer" for tag in spec.domain_tags[:4])
    fallback.extend(
        [
            "music producer",
            "songwriter",
            "film director",
            "brand strategist",
            "education advisor",
            "scientist philosopher",
        ]
    )
    if "music" in spec.domain_tags:
        fallback.extend(
            [
                "Cantopop singer",
                "Cantonese songwriter",
                "Hong Kong music producer",
                "Chinese composer",
            ]
        )
    if "culture_fusion" in spec.domain_tags:
        fallback.extend(
            [
                "cyberpunk writer",
                "Hong Kong film director",
                "futurist musician",
                "Asian visual artist",
            ]
        )
    if llm is None:
        return list(OrderedDict((term.strip(), None) for term in fallback if term.strip()))
    try:
        data = llm.complete_json(
            system_prompt=(
                "Generate high-recall search phrases for finding concrete public figures. "
                "Return JSON only."
            ),
            user_prompt=(
                "Given the scenario below, propose 8-12 short search phrases. "
                "Mix Chinese and English if useful. "
                "JSON schema: {\"search_terms\": [\"...\"]}\n"
                f"scenario={spec.raw_user_query}\n"
                f"domains={spec.domain_tags}"
            ),
        )
        terms = data.get("search_terms", [])
    except Exception:
        terms = fallback
    merged = OrderedDict((term.strip(), None) for term in [*terms, *fallback] if term.strip())
    return list(merged.keys())


def _build_candidate_from_entity(entity_id: str, entity: dict, fallback_label: str = "") -> CelebrityCandidate | None:
    claims = entity.get("claims", {})
    is_human = any(
        snak.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
        for snak in claims.get("P31", [])
    )
    if not is_human:
        return None
    labels = entity.get("labels", {})
    descriptions = entity.get("descriptions", {})
    label_en = labels.get("en", {}).get("value", fallback_label)
    label_zh = labels.get("zh", {}).get("value")
    description = descriptions.get("en", {}).get("value", "")
    birth_year = _parse_birth_year(claims)
    sitelinks = entity.get("sitelinks", {})
    enwiki_title = sitelinks.get("enwiki", {}).get("title")
    wikipedia_url = f"https://en.wikipedia.org/wiki/{enwiki_title.replace(' ', '_')}" if enwiki_title else None
    evidence = _safe_float(0.2 + (len(sitelinks) / 150.0))
    distillability = _safe_float(0.25 + evidence * 0.7)
    domains = [token.strip() for token in description.replace(" and ", ",").split(",") if token.strip()]
    candidate = CelebrityCandidate(
        name=label_zh or label_en or fallback_label,
        name_native=label_zh if label_zh and label_zh != label_en else None,
        wikidata_id=entity_id,
        wikipedia_url=wikipedia_url,
        description=description,
        era=_infer_era(birth_year),
        region="global",
        domains=domains[:6],
        verified_human=True,
        fit_score=0.0,
        anti_fit_penalty=0.0,
        final_score=0.0,
        fit_reasons=[],
        anti_fit_reasons=[],
        controversy_risk=0.25,
        distillability_score=distillability,
        evidence_availability=evidence,
        complementarity_tags=[],
    )
    if not _is_plausible_public_figure_name(candidate.name):
        return None
    return candidate


def _looks_like_person_description(description: str) -> bool:
    lowered = description.lower()
    reject = ["list of", "culture of", "topic", "article", "honorific", "album", "song", "musical genre"]
    if any(token in lowered for token in reject):
        return False
    signals = [
        "actor",
        "actress",
        "singer",
        "musician",
        "rapper",
        "composer",
        "songwriter",
        "director",
        "writer",
        "philosopher",
        "scientist",
        "entrepreneur",
        "athlete",
        "politician",
        "historian",
        "poet",
        "producer",
    ]
    return any(token in lowered for token in signals)


def _is_plausible_public_figure_name(name: str) -> bool:
    value = name.strip()
    if not value:
        return False
    lowered = value.lower()
    reject_exact = {
        "singer-songwriter",
        "record producer",
        "music producer",
        "film director",
        "actor",
        "actress",
        "poet",
        "scientist",
        "entrepreneur",
    }
    if lowered in reject_exact:
        return False
    if value.lower().startswith("list of"):
        return False
    if all(ord(ch) < 128 for ch in value):
        if len(value.split()) < 2 and "(" not in value and ")" not in value:
            return False
    return True


def _fetch_wikipedia_summary_payload(title: str, headers: dict[str, str]) -> dict | None:
    try:
        summary = requests.get(
            f"{WIKIPEDIA_SUMMARY_API}/{quote(title)}",
            headers=headers,
            timeout=10,
        )
        if summary.status_code >= 400:
            return None
        payload = summary.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _retrieve_from_wikipedia_terms(terms: list[str], domain_tags: list[str], max_candidates: int = 80) -> list[CelebrityCandidate]:
    headers = {"User-Agent": "MindForgeStudio/0.3 (contact: local-user)"}
    titles: OrderedDict[str, None] = OrderedDict()
    for term in terms[:8]:
        query = f"{term} person"
        try:
            resp = requests.get(
                WIKIPEDIA_SEARCH_API,
                params={
                    "action": "query",
                    "list": "search",
                    "format": "json",
                    "srsearch": query,
                    "srlimit": 5,
                },
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json().get("query", {}).get("search", []):
                title = str(item.get("title", "")).strip()
                if title and title not in titles:
                    titles[title] = None
                if len(titles) >= max_candidates:
                    break
        except Exception:
            continue
        if len(titles) >= max_candidates:
            break

    candidates_with_score: list[tuple[float, CelebrityCandidate]] = []
    keyword_groups: dict[str, list[str]] = {
        "music": ["music", "musician", "singer", "composer", "lyricist", "cantopop", "cantonese", "producer", "rapper"],
        "culture_fusion": ["cyberpunk", "science fiction", "hong kong", "chinese", "futur", "electronic", "visual", "film"],
        "film": ["film", "director", "screenwriter", "cinema"],
        "branding": ["brand", "marketing", "media"],
    }
    active_keywords: list[str] = []
    for tag in domain_tags:
        active_keywords.extend(keyword_groups.get(tag, []))
    if not active_keywords:
        active_keywords = ["strategy", "culture", "education", "music", "technology"]

    selected_titles = [
        title for title in list(titles.keys())[:max_candidates] if not title.lower().startswith("list of")
    ]
    summaries_by_index: dict[int, dict | None] = {}
    max_workers = min(12, max(1, len(selected_titles)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_wikipedia_summary_payload, title, headers): idx
            for idx, title in enumerate(selected_titles)
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                summaries_by_index[idx] = future.result()
            except Exception:
                summaries_by_index[idx] = None

    for idx, title in enumerate(selected_titles):
        payload = summaries_by_index.get(idx)
        if not payload:
            continue
        description = str(payload.get("description", ""))
        if not description:
            continue
        if description and not _looks_like_person_description(description):
            continue
        candidate_name = str(payload.get("title", title))
        if not _is_plausible_public_figure_name(candidate_name):
            continue
        extract = str(payload.get("extract", ""))
        url = payload.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{quote(title)}")
        text = f"{description} {extract}".lower()
        relevance = sum(text.count(token) for token in active_keywords)
        if "music" in domain_tags and relevance <= 0 and any(x in text for x in ("politician", "astronaut", "military")):
            continue
        candidate = CelebrityCandidate(
            name=candidate_name,
            description=(description + ". " + extract[:180]).strip(),
            era="modern",
            region="global",
            domains=[token.strip() for token in description.replace(" and ", ",").split(",") if token.strip()][:6],
            verified_human=True,
            controversy_risk=0.30,
            distillability_score=0.45,
            evidence_availability=0.38,
            wikipedia_url=url,
        )
        score = float(relevance) + (0.3 if "hong kong" in text else 0.0) + (0.25 if "cantonese" in text else 0.0)
        candidates_with_score.append((score, candidate))
    candidates_with_score.sort(key=lambda x: x[0], reverse=True)
    candidates = [c for _, c in candidates_with_score]
    dedup: OrderedDict[str, CelebrityCandidate] = OrderedDict()
    for candidate in candidates:
        key = candidate.name.strip().lower()
        if key and key not in dedup:
            dedup[key] = candidate
    return list(dedup.values())


def retrieve_candidates(
    spec: ScenarioSpec,
    llm: LLMClient | None,
    max_candidates: int = 80,
) -> list[CelebrityCandidate]:
    retriever = WikidataRetriever()
    terms = _build_search_terms(spec, llm)
    languages = ["zh", "en"] if spec.language.startswith("zh") else ["en", "zh"]
    seen: OrderedDict[str, dict] = OrderedDict()

    try:
        ordered_queries = [(term, language) for term in terms for language in languages]
        max_workers = min(8, max(1, len(ordered_queries)))
        results_by_index: dict[int, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(retriever.search_entities, term, 12, language): idx
                for idx, (term, language) in enumerate(ordered_queries)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results_by_index[idx] = future.result()
                except Exception:
                    results_by_index[idx] = []

        for idx in sorted(results_by_index.keys()):
            for item in results_by_index[idx]:
                entity_id = item.get("id")
                if not entity_id:
                    continue
                if entity_id not in seen:
                    seen[entity_id] = item
                if len(seen) >= max_candidates:
                    break
            if len(seen) >= max_candidates:
                break
    except Exception:
        return _retrieve_from_wikipedia_terms(terms, spec.domain_tags, max_candidates=max_candidates)

    if not seen:
        return _retrieve_from_wikipedia_terms(terms, spec.domain_tags, max_candidates=max_candidates)

    candidates: list[CelebrityCandidate] = []
    chunks = list(_chunks(list(seen.keys()), 40))
    max_workers = min(4, max(1, len(chunks)))
    details_by_chunk: dict[int, dict[str, dict]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(retriever.get_entity_details, chunk): idx for idx, chunk in enumerate(chunks)}
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                details_by_chunk[idx] = future.result()
            except Exception:
                details_by_chunk[idx] = {}

    for idx, chunk in enumerate(chunks):
        details = details_by_chunk.get(idx, {})
        for entity_id in chunk:
            entity = details.get(entity_id)
            if not entity:
                continue
            fallback_label = seen.get(entity_id, {}).get("label", "")
            candidate = _build_candidate_from_entity(entity_id, entity, fallback_label)
            if candidate is not None:
                candidates.append(candidate)
    dedup_by_name: OrderedDict[str, CelebrityCandidate] = OrderedDict()
    for candidate in candidates:
        key = candidate.name.strip().lower()
        if key and key not in dedup_by_name:
            dedup_by_name[key] = candidate
    merged = list(dedup_by_name.values())
    if len(merged) < max(12, int(max_candidates * 0.25)):
        fallback = _retrieve_from_wikipedia_terms(terms, spec.domain_tags, max_candidates=max_candidates)
        for candidate in fallback:
            key = candidate.name.strip().lower()
            if key and key not in dedup_by_name:
                dedup_by_name[key] = candidate
        merged = list(dedup_by_name.values())
    return merged
