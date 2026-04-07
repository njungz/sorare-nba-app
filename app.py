import io
import itertools
import math
from typing import Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

API_URL = "https://api.sorare.com/graphql"
TIMEOUT = 25

st.set_page_config(page_title="Sorare NBA Lineup Optimizer", page_icon="🏀", layout="wide")


def sorare_headers(jwt_token: str = "", api_key: str = "", jwt_aud: str = "") -> Dict[str, str]:
    headers = {"content-type": "application/json"}
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token.strip()}"
    if api_key:
        headers["APIKEY"] = api_key.strip()
    if jwt_aud:
        headers["JWT-AUD"] = jwt_aud.strip()
    return headers


def gql_request(query: str, variables: Optional[dict] = None, jwt_token: str = "", api_key: str = "", jwt_aud: str = "") -> dict:
    response = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers=sorare_headers(jwt_token, api_key, jwt_aud),
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0].get("message", "Sorare GraphQL error"))
    return payload.get("data", {})


def parse_csv(uploaded_file) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.DataFrame(columns=["player_slug", "card_name", "rarity", "multiplier", "manual_projection"])
    df = pd.read_csv(uploaded_file)
    rename_map = {c: c.strip().lower() for c in df.columns}
    df = df.rename(columns=rename_map)
    for col in ["player_slug", "card_name", "rarity", "multiplier", "manual_projection"]:
        if col not in df.columns:
            df[col] = None
    df["multiplier"] = pd.to_numeric(df["multiplier"], errors="coerce").fillna(1.0)
    df["manual_projection"] = pd.to_numeric(df["manual_projection"], errors="coerce")
    return df[["player_slug", "card_name", "rarity", "multiplier", "manual_projection"]].copy()


PLAYER_QUERY = """
query PlayerCardLite($slug: String!) {
  anyPlayer(slug: $slug) {
    slug
    displayName
    sport
    ... on NBAPlayer {
      position
      team {
        fullName
        abbreviation
      }
      age
      lastFiveSo5Appearances
      lastTenSo5Appearances
      tenGameAverage: averageScore(type: LAST_FIFTEEN_SO5_AVERAGE_SCORE)
      nextDailyFixtureProjectedScore
      nextClassicFixtureProjectedScore
      anyFutureGames(first: 3) {
        nodes {
          so5Fixture {
            slug
            gameWeek
          }
          playerGameScore(playerSlug: $slug) {
            projectedScore
          }
        }
      }
    }
  }
}
"""


def fetch_player(slug: str, jwt_token: str = "", api_key: str = "", jwt_aud: str = "") -> dict:
    data = gql_request(PLAYER_QUERY, {"slug": slug}, jwt_token, api_key, jwt_aud)
    player = data.get("anyPlayer")
    if not player:
        raise RuntimeError(f"Player not found for slug: {slug}")

    future_nodes = (((player or {}).get("anyFutureGames") or {}).get("nodes") or [])
    future_scores = []
    future_fixture_slugs = []
    for node in future_nodes:
        pgs = node.get("playerGameScore") or {}
        if pgs.get("projectedScore") is not None:
            future_scores.append(pgs.get("projectedScore"))
        fixture = node.get("so5Fixture") or {}
        if fixture.get("slug"):
            future_fixture_slugs.append(fixture.get("slug"))

    best_future_projection = max(future_scores) if future_scores else None
    return {
        "player_slug": player.get("slug", slug),
        "player_name": player.get("displayName", slug.replace("-", " ").title()),
        "position": player.get("position"),
        "team": ((player.get("team") or {}).get("abbreviation") or (player.get("team") or {}).get("fullName")),
        "age": player.get("age"),
        "last_five": player.get("lastFiveSo5Appearances"),
        "last_ten": player.get("lastTenSo5Appearances"),
        "avg15": player.get("tenGameAverage"),
        "next_daily_projection": player.get("nextDailyFixtureProjectedScore"),
        "next_classic_projection": player.get("nextClassicFixtureProjectedScore"),
        "best_future_projection": best_future_projection,
        "future_fixture_slugs": ", ".join(future_fixture_slugs[:3]),
    }


def score_row(row: pd.Series, mode: str) -> float:
    manual = row.get("manual_projection")
    if pd.notna(manual):
        base = float(manual)
    elif mode == "Classic":
        base = row.get("next_classic_projection")
    elif mode == "Daily":
        base = row.get("next_daily_projection")
    else:
        candidates = [row.get("best_future_projection"), row.get("next_classic_projection"), row.get("next_daily_projection"), row.get("avg15")]
        candidates = [float(x) for x in candidates if x is not None and not (isinstance(x, float) and math.isnan(x))]
        base = max(candidates) if candidates else None

    if base is None or (isinstance(base, float) and math.isnan(base)):
        base = 0.0
    return float(base) * float(row.get("multiplier", 1.0) or 1.0)


def optimize_lineup(df: pd.DataFrame, lineup_size: int = 5, cap: Optional[float] = None) -> pd.DataFrame:
    if len(df) < lineup_size:
        return pd.DataFrame()

    best_score = -1.0
    best_idx = None
    for combo in itertools.combinations(df.index.tolist(), lineup_size):
        subset = df.loc[list(combo)]
        if cap is not None and subset["cap_value"].sum() > cap:
            continue
        score = subset["effective_projection"].sum()
        if score > best_score:
            best_score = score
            best_idx = combo

    if best_idx is None:
        return pd.DataFrame()
    return df.loc[list(best_idx)].sort_values("effective_projection", ascending=False).reset_index(drop=True)


st.title("🏀 Sorare NBA Lineup Optimizer")
st.caption("Paste Sorare NBA player slugs or upload a CSV, fetch live projections from Sorare, and build the best 5-player lineup.")

with st.sidebar:
    st.header("API settings")
    jwt_token = st.text_input("Sorare JWT token", type="password", help="Optional for public player queries. Useful if Sorare tightens access.")
    jwt_aud = st.text_input("JWT-AUD", help="Only needed if your token requires it.")
    api_key = st.text_input("Sorare API key", type="password", help="Optional. Only for higher rate limits.")
    projection_mode = st.selectbox("Projection source", ["Best available", "Classic", "Daily"])
    lineup_size = st.slider("Lineup size", min_value=3, max_value=8, value=5)
    use_cap = st.toggle("Use cap rule", value=False)
    cap_value = st.number_input("Cap total", min_value=0.0, value=120.0, step=1.0, disabled=not use_cap)

left, right = st.columns([1.15, 1])

with left:
    st.subheader("1) Load your candidate pool")
    st.markdown(
        "Upload a CSV with columns like `player_slug`, `card_name`, `rarity`, `multiplier`, `manual_projection`, `cap_value`, or paste one slug per line below."
    )
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    pasted = st.text_area(
        "Or paste player slugs",
        placeholder="victor-wembanyama-20040104\nnikola-jokic-19950219\nshai-gilgeous-alexander-19980712",
        height=160,
    )

    candidates = parse_csv(uploaded)
    pasted_slugs = [line.strip() for line in pasted.splitlines() if line.strip()]
    if pasted_slugs:
        pasted_df = pd.DataFrame({"player_slug": pasted_slugs})
        for col in ["card_name", "rarity", "multiplier", "manual_projection"]:
            if col not in pasted_df.columns:
                pasted_df[col] = None
        pasted_df["multiplier"] = 1.0
        candidates = pd.concat([candidates, pasted_df], ignore_index=True)

    if len(candidates) == 0:
        st.info("Add some player slugs or upload a CSV to begin.")

    st.dataframe(candidates, use_container_width=True, hide_index=True)

with right:
    st.subheader("2) Fetch Sorare data")
    fetch_clicked = st.button("Fetch player data", type="primary", use_container_width=True, disabled=len(candidates) == 0)

    if fetch_clicked:
        rows: List[dict] = []
        errors: List[str] = []
        unique = candidates.dropna(subset=["player_slug"]).copy()
        unique["player_slug"] = unique["player_slug"].astype(str).str.strip()
        unique = unique[unique["player_slug"] != ""]

        progress = st.progress(0)
        for i, record in enumerate(unique.to_dict("records"), start=1):
            slug = record["player_slug"]
            try:
                api_row = fetch_player(slug, jwt_token=jwt_token, api_key=api_key, jwt_aud=jwt_aud)
                merged = {**record, **api_row}
                rows.append(merged)
            except Exception as exc:
                errors.append(f"{slug}: {exc}")
            progress.progress(i / max(len(unique), 1))

        if rows:
            result_df = pd.DataFrame(rows)
            if "cap_value" not in result_df.columns:
                result_df["cap_value"] = result_df["avg15"].fillna(0)
            result_df["cap_value"] = pd.to_numeric(result_df["cap_value"], errors="coerce").fillna(result_df["avg15"]).fillna(0)
            result_df["effective_projection"] = result_df.apply(lambda row: score_row(row, projection_mode), axis=1)
            st.session_state["player_pool"] = result_df
            st.success(f"Fetched {len(result_df)} players.")
        if errors:
            st.warning("Some rows failed to load:")
            st.code("\n".join(errors))

pool = st.session_state.get("player_pool")
if pool is not None and len(pool) > 0:
    st.subheader("3) Review player pool")
    display_cols = [
        "player_name", "player_slug", "position", "team", "rarity", "multiplier",
        "avg15", "next_classic_projection", "next_daily_projection", "best_future_projection",
        "effective_projection", "cap_value", "future_fixture_slugs"
    ]
    existing_cols = [c for c in display_cols if c in pool.columns]
    edited = st.data_editor(pool[existing_cols], use_container_width=True, hide_index=True)

    csv_bytes = edited.to_csv(index=False).encode("utf-8")
    st.download_button("Download player pool CSV", csv_bytes, file_name="sorare_nba_player_pool.csv", mime="text/csv")

    st.subheader("4) Best lineup")
    optimized = pool.copy()
    lineup = optimize_lineup(optimized, lineup_size=lineup_size, cap=cap_value if use_cap else None)
    if len(lineup) == 0:
        st.error("No valid lineup found. Add more players or relax the cap.")
    else:
        st.metric("Projected lineup total", f"{lineup['effective_projection'].sum():.2f}")
        if use_cap:
            st.metric("Cap used", f"{lineup['cap_value'].sum():.1f} / {cap_value:.1f}")
        st.dataframe(
            lineup[[c for c in ["player_name", "position", "team", "rarity", "multiplier", "cap_value", "effective_projection"] if c in lineup.columns]],
            use_container_width=True,
            hide_index=True,
        )

st.divider()
with st.expander("Expected CSV format"):
    sample = pd.DataFrame(
        [
            {
                "player_slug": "victor-wembanyama-20040104",
                "card_name": "Victor Wembanyama Limited",
                "rarity": "limited",
                "multiplier": 1.0,
                "manual_projection": None,
                "cap_value": 35,
            },
            {
                "player_slug": "nikola-jokic-19950219",
                "card_name": "Nikola Jokic Limited",
                "rarity": "limited",
                "multiplier": 1.0,
                "manual_projection": None,
                "cap_value": 41,
            },
        ]
    )
    st.dataframe(sample, use_container_width=True, hide_index=True)
    st.markdown(
        "Use `manual_projection` when you want to override Sorare's projected score with your own model."
    )
