import streamlit as st
import requests
import pandas as pd
from itertools import combinations

st.set_page_config(page_title="Sorare NBA Optimizer", layout="wide")

st.title("🏀 Sorare NBA Auto Lineup Optimizer")

# --------------------------
# GraphQL helper
# --------------------------
API_URL = "https://api.sorare.com/graphql"

def run_query(query, variables):
    res = requests.post(API_URL, json={
        "query": query,
        "variables": variables
    })
    return res.json()

# --------------------------
# Fetch user cards + player data
# --------------------------
def get_user_players(username):
    query = """
    query($username: String!) {
      user(slug: $username) {
        cards(first: 50) {
          nodes {
            player {
              displayName
              slug
            }
          }
        }
      }
    }
    """

    data = run_query(query, {"username": username})

    try:
        cards = data["data"]["user"]["cards"]["nodes"]
    except:
        return None

    players = []
    for c in cards:
        if c["player"]:
            players.append({
                "name": c["player"]["displayName"],
                "slug": c["player"]["slug"]
            })

    return players

# --------------------------
# Fake projection model (no JWT)
# --------------------------
def get_projection(player_slug):
    # Simulated projection (replace with real data if JWT later)
    import random
    return round(random.uniform(20, 50), 2)

# --------------------------
# UI
# --------------------------
username = st.text_input("Enter your Sorare username")

if username:
    players = get_user_players(username)

    if not players:
        st.error("❌ Could not fetch players")
        st.stop()

    st.success(f"✅ Loaded {len(players)} players")

    # Build dataframe
    df = pd.DataFrame(players)

    # Auto projections
    st.info("⚡ Generating projections...")
    df["projection"] = df["slug"].apply(get_projection)

    st.dataframe(df, use_container_width=True)

    # --------------------------
    # Optimizer
    # --------------------------
    st.subheader("⚙️ Lineup Settings")

    lineup_size = st.slider("Lineup size", 3, 5, 5)

    if st.button("🚀 Optimize Lineup"):
        players_list = df.to_dict("records")

        best_score = 0
        best_lineup = None

        for combo in combinations(players_list, lineup_size):
            total_score = sum(p["projection"] for p in combo)

            if total_score > best_score:
                best_score = total_score
                best_lineup = combo

        if best_lineup:
            st.success("🏆 Best Lineup Found!")

            result_df = pd.DataFrame(best_lineup)
            st.dataframe(result_df, use_container_width=True)

            st.metric("Total Projection", round(best_score, 2))
