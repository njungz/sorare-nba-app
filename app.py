import streamlit as st
import requests

st.set_page_config(page_title="Sorare NBA Optimizer", layout="wide")

st.title("🏀 Sorare NBA Lineup Optimizer")

# --- LOGIN ---
st.sidebar.header("🔐 Login")

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Password", type="password")

if not email or not password:
    st.warning("Enter your email & password")
    st.stop()

# --- AUTH REQUEST ---
url = "https://api.sorare.com/graphql"

auth_query = {
    "query": """
    mutation signIn($input: signInInput!) {
      signIn(input: $input) {
        currentUser { slug }
        jwtToken(aud: "sorare-nba-lineup-app") {
          token
        }
      }
    }
    """,
    "variables": {
        "input": {
            "email": email,
            "password": password
        }
    }
}

auth_res = requests.post(url, json=auth_query)

if auth_res.status_code != 200:
    st.error("Login failed")
    st.stop()

auth_data = auth_res.json()

try:
    token = auth_data["data"]["signIn"]["jwtToken"]["token"]
except:
    st.error("Invalid login or 2FA enabled")
    st.stop()

# --- FETCH CARDS ---
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

query = """
query MyCards {
  currentUser {
    basketballCards(first: 50) {
      nodes {
        player { displayName }
        averageScore(type: LAST_FIVE_SO5_AVERAGE_SCORE)
        latestFixtureStats { score }
        xp
      }
    }
  }
}
"""

res = requests.post(url, json={"query": query}, headers=headers)

if res.status_code != 200:
    st.error("Failed to fetch cards")
    st.stop()

data = res.json()

try:
    cards = data["data"]["currentUser"]["basketballCards"]["nodes"]
except:
    st.error("No data found")
    st.stop()

# --- PROCESS ---
players = []

for c in cards:
    name = c["player"]["displayName"]
    l5 = c.get("averageScore") or 0
    last = c.get("latestFixtureStats")
    last_score = last["score"] if last else 0
    xp = c.get("xp") or 0

    score = l5 * 0.6 + last_score * 0.3 + xp * 0.1

    players.append({
        "name": name,
        "score": score,
        "l5": l5,
        "last": last_score
    })

players = sorted(players, key=lambda x: x["score"], reverse=True)

# --- UI ---
st.subheader("🔥 Best Lineup")

for i, p in enumerate(players[:5], 1):
    st.write(f"{i}. {p['name']} — {round(p['score'],1)}")

st.subheader("📊 All Players")
st.dataframe(players)
