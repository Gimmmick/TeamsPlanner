import json
import os
import pandas as pd
import streamlit as st

DATA_FILE = "roster.json"

# --- Data Management Functions ---
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                # Migration for old single-list format
                if isinstance(data, list):
                    return {"Default Roster": data}
                return data
        except Exception:
            return {"Default Roster": []}
    return {"Default Roster": []}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Format Groups Text Export ---
def generate_group_text(players, leaders, num_teams):
    output_lines = []
    for g in range(1, num_teams + 1):
        leader_name = leaders[g - 1]
        # Collect all members assigned to group g
        group_members = [p["nickname"] for p in players if p.get("group") == g]
        
        # Ensure the leader comes first, followed by remaining group members
        other_members = [name for name in group_members if name != leader_name]
        ordered_members = [leader_name] + other_members if leader_name in group_members else group_members
        
        # Format: Group X:\nLeader, Player2, Player3...
        formatted_group = f"Group {g}:\n" + ", ".join(ordered_members)
        output_lines.append(formatted_group)
    
    return "\n\n".join(output_lines)

# --- Balancing Algorithm ---
def auto_balance(players, leaders, num_teams):
    # Reset groups
    for p in players:
        p["group"] = 0

    groups = {g: [] for g in range(1, num_teams + 1)}
    group_powers = {g: 0 for g in range(1, num_teams + 1)}

    # Assign Leaders
    for idx, lname in enumerate(leaders, start=1):
        for p in players:
            if p["nickname"] == lname:
                p["group"] = idx
                groups[idx].append(p)
                group_powers[idx] += p["power"]
                break

    # Get remaining unassigned players sorted by power (descending)
    remaining = [p for p in players if p["group"] == 0]
    remaining.sort(key=lambda x: x["power"], reverse=True)

    # Greedily assign highest remaining power to lowest current group power
    for p in remaining:
        target_group = min(group_powers, key=group_powers.get)
        p["group"] = target_group
        groups[target_group].append(p)
        group_powers[target_group] += p["power"]

    return players

# --- App UI & Logic ---
st.set_page_config(page_title="Teams Planner", layout="wide")
st.title("Teams Planner")

if "rosters" not in st.session_state:
    st.session_state.rosters = load_data()

# --- Sidebar: Multi-Roster Manager ---
st.sidebar.header("Roster Management")

roster_names = list(st.session_state.rosters.keys())
selected_roster = st.sidebar.selectbox("Select Active Roster", roster_names)

# Add New Roster
with st.sidebar.expander("➕ Create New Roster"):
    new_roster_name = st.text_input("New Roster Name")
    if st.button("Create Roster") and new_roster_name:
        if new_roster_name not in st.session_state.rosters:
            st.session_state.rosters[new_roster_name] = []
            save_data(st.session_state.rosters)
            st.rerun()
        else:
            st.sidebar.error("Roster already exists!")

# Delete Roster
if len(roster_names) > 1:
    with st.sidebar.expander("🗑️ Delete Current Roster"):
        st.write(f"Delete **{selected_roster}**?")
        if st.button("Confirm Delete Roster", type="primary"):
            del st.session_state.rosters[selected_roster]
            save_data(st.session_state.rosters)
            st.rerun()

current_players = st.session_state.rosters[selected_roster]

st.sidebar.markdown("---")

# --- Clear Current Roster ---
with st.sidebar:
    st.markdown("### Clear Active Roster")
    with st.popover("Clear Roster"):
        st.write(f"Are you sure you want to delete **all players** from **{selected_roster}**?")
        if st.button("Yes, Clear All Players", type="primary"):
            st.session_state.rosters[selected_roster] = []
            save_data(st.session_state.rosters)
            st.rerun()

# --- Roster Management ---
st.header(f"1. Add players: {selected_roster}")

with st.form("add_player_form", clear_on_submit=True):
    col1, col2 = st.columns([2, 1])
    new_name = col1.text_input("Player Nickname")
    new_power = col2.number_input("Power", min_value=0, step=100000)
    submitted = st.form_submit_button("Add Player")

    if submitted and new_name:
        # Check duplicate inside active roster
        if not any(p["nickname"] == new_name for p in current_players):
            current_players.append({"nickname": new_name, "power": new_power, "group": 0})
            st.session_state.rosters[selected_roster] = current_players
            save_data(st.session_state.rosters)
            st.rerun()
        else:
            st.error("Player already exists in this roster!")

# Editable Roster Display
if current_players:
    st.subheader("Current Players (Click power or nickname to edit directly)")
    
    df_roster = pd.DataFrame(current_players)
    
    # Editable dataframe for direct power/nickname modification
    edited_df = st.data_editor(
        df_roster[["nickname", "power"]],
        use_container_width=True,
        num_rows="fixed",
        key=f"roster_editor_{selected_roster}"
    )
    
    # Save edits back to session state if values changed
    updated_players = []
    for idx, row in edited_df.iterrows():
        orig_group = current_players[idx].get("group", 0) if idx < len(current_players) else 0
        updated_players.append({
            "nickname": str(row["nickname"]),
            "power": int(row["power"]),
            "group": orig_group
        })
    
    if updated_players != current_players:
        st.session_state.rosters[selected_roster] = updated_players
        save_data(st.session_state.rosters)
        st.rerun()

    with st.expander("Remove a Single Player"):
        player_to_remove = st.selectbox("Select player to delete", [p["nickname"] for p in current_players])
        if st.button("Delete Player"):
            st.session_state.rosters[selected_roster] = [p for p in current_players if p["nickname"] != player_to_remove]
            save_data(st.session_state.rosters)
            st.rerun()

st.markdown("---")

# --- Group & Leader Balancing ---
st.header(f"2. Group Distribution")

all_nicknames = [p["nickname"] for p in current_players]

# Dynamic Team Count Selection
num_teams = st.number_input("Number of Teams/Groups", min_value=2, max_value=10, value=3, step=1, key=f"num_teams_{selected_roster}")

if len(all_nicknames) >= num_teams:
    st.subheader("Select Group Leaders")
    leader_cols = st.columns(num_teams)
    leaders = []

    for i in range(num_teams):
        with leader_cols[i]:
            default_index = min(i, len(all_nicknames) - 1)
            selected_leader = st.selectbox(
                f"Group {i+1} Leader",
                all_nicknames,
                index=default_index,
                key=f"l{i+1}_{selected_roster}_{num_teams}"
            )
            leaders.append(selected_leader)

    if len(set(leaders)) < num_teams:
        st.warning(f"Please select {num_teams} unique leaders.")
    else:
        if st.button("Auto-Balance Remaining Players", type="primary"):
            st.session_state.rosters[selected_roster] = auto_balance(current_players, leaders, num_teams)
            save_data(st.session_state.rosters)
            st.rerun()

    st.markdown("---")
    st.subheader("3. Group Overview & Manual Adjustments")

    cols = st.columns(num_teams)

    for g in range(1, num_teams + 1):
        with cols[g - 1]:
            group_members = [p for p in current_players if p.get("group") == g]
            total_power = sum(p["power"] for p in group_members)
            
            st.markdown(f"### Group {g}")
            st.markdown(f"**Total Power:** {total_power:,}")
            st.markdown(f"**Leader:** {leaders[g-1]}")
            st.markdown("---")

            for p in group_members:
                p_col1, p_col2 = st.columns([2, 1])
                is_leader = "👑 " if p["nickname"] in leaders else ""
                p_col1.write(f"{is_leader}**{p['nickname']}** ({p['power']:,})")
                
                new_group = p_col2.selectbox(
                    "Group", 
                    options=list(range(1, num_teams + 1)), 
                    index=g - 1, 
                    key=f"override_{selected_roster}_{p['nickname']}_{num_teams}"
                )
                if new_group != g:
                    p["group"] = new_group
                    save_data(st.session_state.rosters)
                    st.rerun()
                    
    st.markdown("---")
    
    # --- Download Text Export Section ---
    group_text = generate_group_text(current_players, leaders)
    
    st.download_button(
        label="📥 Download Group Assignments (.txt)",
        data=group_text,
        file_name=f"{selected_roster.lower().replace(' ', '_')}_groups.txt",
        mime="text/plain"
    )
    
else:
    st.info("Add at least 3 players to start group assignments.")
