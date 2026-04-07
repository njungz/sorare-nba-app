import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Sorare NBA Optimizer", layout="wide")
st.title("🏀 Sorare NBA Lineup Optimizer")

API_URL = "https://api.sorare.com/graphql"
AUD = "sorare-nba-lineup-app"

SIGNIN_QUERY = """
mutation SignInMutation($input: signInInput!) {
  signIn(input: $input) {
    currentUser {
      slug
    }
    jwtToken(aud: "sorare-nba-lineup-app") {
      token
      expiredAt
    }
    otpSessionChallenge
    errors {
      message
    }
  }
}
"""

CARDS_QUERY = """
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

def post_graphql(query: str, variables=None, headers=None):
    resp = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers=headers or {"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def extract_errors(payload):
    top = payload.get("errors") or []
    if top:
        return [e.get("message", "Unknown error") for e in top]
    sign_in = payload.get("data", {}).get("signIn", {})
    nested = sign_in.get("errors") or []
    return [e.get("message", "Unknown error") for e in nested]

def login_step_1(email: str, password: str):
    variables = {"input": {"email": email, "password": password}}
    return post_graphql(SIGNIN_QUERY, variables=variables)

def login_step_2(challenge: str, otp_code: str):
    variables = {
        "input": {
            "otpSessionChallenge": challenge,
            "otpAttempt": otp_code,
        }
    }
    return post_graphql(SIGNIN_QUERY, variables=variables)

def fetch_cards(jwt_token: str):
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    return post_graphql(CARDS_QUERY, headers=headers)

def rank_cards(cards):
    ranked = []
    for card in cards:
        player = card.get("player") or {}
        latest = card.get("latestFixtureStats") or {}
        l5 = card.get("averageScore") or 0
        last_score = latest.get("score") or 0
        xp = card.get("xp") or 0

        # Simple starter scoring model
        score = (l5 * 0.6) + (last_score * 0.3) + (xp * 0.1)

        ranked.append({
            "Player": player.get("displayName", "Unknown"),
            "L5": l5,
            "Last": last_score,
            "XP": xp,
            "Score": round(score, 2),
        })

    ranked.sort(key=lambda x: x["Score"], reverse=True)
    return ranked

if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = None
if "otp_session_challenge" not in st.session_state:
    st.session_state.otp_session_challenge = None
if "login_email" not in st.session_state:
    st.session_state.login_email = ""

with st.sidebar:
    st.header("🔐 Login")

    if not st.session_state.jwt_token:
        email = st.text_input("Email", value=st.session_state.login_email)
        password = st.text_input("Password", type="password")

        col1, col2 = st.columns(2)
        with col1:
            start_login = st.button("Start login", use_container_width=True)
        with col2:
            clear_login = st.button("Reset", use_container_width=True)

        if clear_login:
            st.session_state.jwt_token = None
            st.session_state.otp_session_challenge = None
            st.session_state.login_email = ""
            st.rerun()

        if start_login:
            if not email or not password:
                st.error("Enter your email and password.")
            else:
                st.session_state.login_email = email
                try:
                    payload = login_step_1(email, password)
                    sign_in = payload.get("data", {}).get("signIn", {})
                    errors = extract_errors(payload)

                    jwt = (sign_in.get("jwtToken") or {}).get("token")
                    otp_challenge = sign_in.get("otpSessionChallenge")

                    if jwt:
                        st.session_state.jwt_token = jwt
                        st.session_state.otp_session_challenge = None
                        st.success("Logged in.")
                        st.rerun()
                    elif otp_challenge:
                        st.session_state.otp_session_challenge = otp_challenge
                        st.info("2FA code required. Check your email/authenticator and enter the code below.")
                    elif errors:
                        st.error("Login failed: " + " | ".join(errors))
                    else:
                        st.error("Login failed.")
                except Exception as e:
                    st.error(f"Login error: {e}")

        if st.session_state.otp_session_challenge and not st.session_state.jwt_token:
            st.subheader("2FA verification")
            otp_code = st.text_input("6-digit 2FA code", max_chars=6)

            if st.button("Verify 2FA", use_container_width=True):
                if not otp_code:
                    st.error("Enter your 2FA code.")
                else:
                    try:
                        payload = login_step_2(st.session_state.otp_session_challenge, otp_code)
                        sign_in = payload.get("data", {}).get("signIn", {})
                        errors = extract_errors(payload)
                        jwt = (sign_in.get("jwtToken") or {}).get("token")

                        if jwt:
                            st.session_state.jwt_token = jwt
                            st.session_state.otp_session_challenge = None
                            st.success("2FA complete.")
                            st.rerun()
                        elif errors:
                            st.error("2FA failed: " + " | ".join(errors))
                        else:
                            st.error("2FA failed.")
                    except Exception as e:
                        st.error(f"2FA error: {e}")
    else:
        st.success("Authenticated")
        if st.button("Log out", use_container_width=True):
            st.session_state.jwt_token = None
            st.session_state.otp_session_challenge = None
            st.rerun()

if not st.session_state.jwt_token:
    st.stop()

try:
    with st.spinner("Loading your Sorare NBA cards..."):
        payload = fetch_cards(st.session_state.jwt_token)

    current_user = payload.get("data", {}).get("currentUser")
    if not current_user:
        st.error("Authenticated, but no current user data was returned.")
        st.stop()

    cards = current_user.get("basketballCards", {}).get("nodes", [])
    ranked = rank_cards(cards)

    st.subheader("🔥 Best 5 lineup picks")
    for i, row in enumerate(ranked[:5], start=1):
        st.write(f"**#{i} — {row['Player']}**")
        st.write(f"L5: {row['L5']} | Last: {row['Last']} | XP: {row['XP']} | Score: {row['Score']}")
        st.divider()

    st.subheader("📊 All cards ranked")
    st.dataframe(pd.DataFrame(ranked), use_container_width=True)

except Exception as e:
    st.error(f"Failed to load cards: {e}")
