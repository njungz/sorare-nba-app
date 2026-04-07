import streamlit as st
import requests

st.set_page_config(page_title="Sorare NBA Optimizer", layout="wide")

st.title("🏀 Sorare NBA Lineup Optimizer")

# --- AUTH ---
st.sidebar.header("🔐 Login")

jwt_token = st.sidebar.text_input("Paste your Sorare JWT Token", type="password")

if not jwt_token:
    st.warning("Enter your JWT token to continue")
    st.stop()

# --- GRAPHQL QUERY ---
url = "https://api.sorare.com/graphql"

headers = {
    "Authorization": f"Bearer {jwt_token}",
    "Content-Type": "application/json"
}

query = """
query MyCards {
  currentUser {
    basketballCards(first: 50) {
      nodes {
        slug
        player {
          displayName
        }
        averageScore(type: LAST_FIVE_SO5_AVERAGE_SCORE)
        latestFixtureStats {
          score
        }
        xp
      }
    }
  }
}
"""

# --- FETCH DATA ---
with st.spinner("Loading your cards..."):
    response = requests.post(url, json={"query": query}, headers=headers)

if response.status_code != 200:
    st.error("❌ Failed to connect to Sorare API")
    st.stop()

data = response.json()

try:
    cards = data["data"]["currentUser"]["basketballCards"]["nodes"]
except:
    st.error("❌ Invalid token or no data found")
    st.stop()

# --- PROCESS ---
players = []

for card in cards:
    name = card["player"]["displayName"]
    l5 = card.get("averageScore") or 0
    last = card.get("latestFixtureStats")
    last_score = last["score"] if last else 0
    xp = card.get("xp") or 0

    score = l5 * 0.6 + last_score * 0.3 + xp * 0.1

    players.append({
        "name": name,
        "L5": l5,
        "Last": last_score,
        "XP": xp,
        "Score": score
    })

# --- SORT ---
players = sorted(players, key=lambda x: x["Score"], reverse=True)

# --- DISPLAY ---
st.subheader("🔥 Best Lineup Picks")

top5 = players[:5]

for i, p in enumerate(top5, 1):
    st.write(f"#{i} — {p['name']}")
    st.progress(min(p["Score"] / 100, 1.0))
    st.write(f"L5: {p['L5']} | Last: {p['Last']} | XP: {p['XP']}")
    st.divider()

# --- FULL LIST ---
st.subheader("📊 All Players Ranked")

st.dataframe(players)
