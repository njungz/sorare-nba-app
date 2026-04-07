import streamlit as st
import requests
import pandas as pd
from itertools import combinations

st.set_page_config(page_title="Sorare NBA Username Optimizer", layout="wide")

API_URL = "https://api.sorare.com/graphql"


def run_query(query: str, variables: dict | None = None):
    try:
        response = requests.post(
            API_URL,
            json={"query": query, "variables": variables or {}},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"errors": [{"message": f"Network error: {e}"}]}


def get_user_nba_cards(username: str):
    query = """
    query GetUserNBACards($slug: String!) {
      user(slug: $slug) {
        nickname
        cards(first: 50, sport: NBA) {
          nodes {
            slug
            sport
            rarityTyped
            season
            anyPlayer {
              displayName
              slug
            }
          }
        }
      }
    }
    """

    data = run_query(query, {"slug": username.strip()})

    if data.get("errors"):
        return None, "; ".join(err.get("message", "Unknown error") for err in data["errors"])

    user = data.get("data", {}).get("user")
    if not user:
        return None, "User not found. Make sure you entered the exact Sorare manager slug."

    nodes = user.get("cards", {}).get("nodes", [])
    rows = []

    for card in nodes:
        any_player = card.get("anyPlayer")
        if not any_player:
            continue

        rows.append(
            {
                "card_slug": card.get("slug"),
                "name": any_player.get("displayName"),
                "player_slug": any_player.get("slug"),
                "rarity": card.get("rarityTyped"),
                "season": card.get("season"),
            }
        )

    if not rows:
        return [], f"User '{user.get('nickname', username)}' was found, but no public NBA cards were returned."

    return rows, None


def simple_projection(row):
    rarity_bonus = {
        "common": 0,
        "limited": 1,
        "rare": 2,
        "super_rare": 3,
        "unique": 5,
    }

    rarity_key = str(row.get("rarity", "")).lower()
    season_val = row.get("season") or 0

    base = 20
    proj = base + rarity_bonus.get(rarity_key, 0)

    try:
        if int(season_val) >= 2025:
            proj += 2
    except Exception:
        pass

    return float(proj)


st.title("🏀 Sorare NBA Lineup Optimizer")
st.caption("Username-only mode")

username = st.text_input("Enter your Sorare username / manager slug")

if st.button("Load my NBA cards"):
    if not username.strip():
        st.warning("Enter your Sorare username first.")
        st.stop()

    with st.spinner("Fetching public NBA cards..."):
        cards, error = get_user_nba_cards(username)

    if error:
        st.error(error)
        st.stop()

    if not cards:
        st.warning("No public NBA cards found for that account.")
        st.stop()

    df = pd.DataFrame(cards)
    df["projection"] = df.apply(simple_projection, axis=1)

    st.success(f"Loaded {len(df)} NBA cards.")
    st.dataframe(df, use_container_width=True)

    lineup_size = st.slider("Lineup size", min_value=3, max_value=5, value=5)

    players = df.to_dict("records")
    if len(players) < lineup_size:
        st.warning(f"You only have {len(players)} NBA cards loaded.")
        st.stop()

    best_score = -1.0
    best_lineup = None

    for combo in combinations(players, lineup_size):
        total = sum(p["projection"] for p in combo)
        if total > best_score:
            best_score = total
            best_lineup = combo

    if best_lineup:
        result_df = pd.DataFrame(best_lineup)[
            ["name", "rarity", "season", "projection", "player_slug", "card_slug"]
        ]
        st.subheader("Best lineup")
        st.dataframe(result_df, use_container_width=True)
        st.metric("Projected total", round(best_score, 2))
