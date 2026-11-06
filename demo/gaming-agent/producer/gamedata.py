"""Static game/persona/player definitions shared by the generator (and, later, the trigger UI).

Three fictional games (no real game IP), each with its own zones, bosses, and store SKUs.
Boss/zone/SKU ids defined here must match the mock catalog in the tools UDF (DESIGN.md §5).

Nothing here touches Kafka; see kafka_io.py for serialization and generate_events.py for the loop.
"""

import random

# ---------------------------------------------------------------------------
# Games: zones (min_level ascending), bosses, regular enemies, store SKUs.
# `counters` lists boss ids a SKU is especially useful against (catalog hint).
# ---------------------------------------------------------------------------

GAMES = {
    "ember_throne": {
        "classes": ["warrior", "mage", "ranger"],
        "zones": [
            {"id": "ashen_keep", "min_level": 1, "boss": "ash_brute", "enemies": ["ember_imp", "cinder_hound"]},
            {"id": "frostfall_pass", "min_level": 15, "boss": "ice_golem", "enemies": ["frost_wraith", "snow_stalker"]},
            {"id": "cinder_depths", "min_level": 30, "boss": "cinder_wyrm", "enemies": ["magma_crawler", "ash_cultist"]},
            {"id": "obsidian_citadel", "min_level": 45, "boss": "void_regent", "enemies": ["void_knight", "shade_priest"]},
        ],
        "skus": [
            {"sku": "frost_ward_bundle", "price": 4.99, "counters": ["ice_golem"]},
            {"sku": "fire_resist_bundle", "price": 4.99, "counters": ["cinder_wyrm", "ash_brute"]},
            {"sku": "void_shield_pack", "price": 6.99, "counters": ["void_regent"]},
            {"sku": "healing_potion_10", "price": 1.99, "counters": []},
            {"sku": "heroic_gear_upgrade", "price": 9.99, "counters": []},
            {"sku": "xp_boost_24h", "price": 2.99, "counters": []},
        ],
    },
    "starlane_arena": {
        "classes": ["assault", "medic", "engineer"],
        "zones": [
            {"id": "dock_9", "min_level": 1, "boss": "drone_warden", "enemies": ["scrap_drone", "dock_raider"]},
            {"id": "nebula_ring", "min_level": 15, "boss": "storm_leviathan", "enemies": ["ion_sprite", "ring_pirate"]},
            {"id": "debris_field", "min_level": 30, "boss": "scrap_tyrant", "enemies": ["salvage_bot", "wreck_hunter"]},
            {"id": "core_reactor", "min_level": 45, "boss": "reactor_titan", "enemies": ["coolant_golem", "plasma_sentry"]},
        ],
        "skus": [
            {"sku": "ion_shield_pack", "price": 3.99, "counters": ["storm_leviathan"]},
            {"sku": "emp_grenade_bundle", "price": 4.99, "counters": ["drone_warden", "scrap_tyrant"]},
            {"sku": "reactor_suit_mk2", "price": 11.99, "counters": ["reactor_titan"]},
            {"sku": "medkit_pack_10", "price": 1.99, "counters": []},
            {"sku": "weapon_mod_kit", "price": 7.99, "counters": []},
            {"sku": "battle_pass_boost", "price": 4.99, "counters": []},
        ],
    },
    "tidal_rogue": {
        "classes": ["harpooner", "navigator", "buccaneer"],
        "zones": [
            {"id": "shallows", "min_level": 1, "boss": "brine_crab_king", "enemies": ["reef_snapper", "tide_crab"]},
            {"id": "kelp_maze", "min_level": 15, "boss": "hydra_mother", "enemies": ["kelp_lurker", "eel_swarm"]},
            {"id": "sunken_fleet", "min_level": 30, "boss": "ghost_admiral", "enemies": ["drowned_gunner", "barnacle_ghoul"]},
            {"id": "abyssal_trench", "min_level": 45, "boss": "maw_of_the_deep", "enemies": ["anglerfish", "abyss_horror"]},
        ],
        "skus": [
            {"sku": "venom_antidote_bundle", "price": 3.99, "counters": ["hydra_mother"]},
            {"sku": "spectral_cannon_pack", "price": 5.99, "counters": ["ghost_admiral"]},
            {"sku": "pressure_hull_upgrade", "price": 9.99, "counters": ["maw_of_the_deep"]},
            {"sku": "repair_kit_5", "price": 1.49, "counters": []},
            {"sku": "lucky_loot_crate", "price": 2.99, "counters": []},
            {"sku": "rum_ration_bundle", "price": 0.99, "counters": []},
        ],
    },
}

REGIONS = ["us-east", "us-west", "eu-west", "kr", "jp", "sea"]

# ---------------------------------------------------------------------------
# Personas. death_p = chance a fight ends in a death. Normal play must stay BELOW the
# struggle filter (DESIGN.md §4): scenes are capped at max_deaths (<=2) with at most one
# quest fail, and each player waits scene_gap seconds between scenes (> the ~10-15 s
# SESSION gap) so two scenes never merge into one window.
# ---------------------------------------------------------------------------

PERSONAS = {
    "casual": dict(
        tier="F2P", level=(3, 20), fights=(2, 5), death_p=0.25, max_deaths=2, dmg=(5, 40),
        scene_gap=(45, 120), store_view_p=0.15, purchase_p=0.01, quest_p=0.3, quest_fail_p=0.3,
        lifetime=(0, 5), cap=None, minor=False,
    ),
    "grinder": dict(
        tier="F2P", level=(20, 40), fights=(5, 10), death_p=0.12, max_deaths=2, dmg=(10, 60),
        scene_gap=(30, 75), store_view_p=0.08, purchase_p=0.01, quest_p=0.4, quest_fail_p=0.2,
        lifetime=(0, 20), cap=None, minor=False,
    ),
    "veteran": dict(
        tier="spender", level=(40, 60), fights=(5, 10), death_p=0.05, max_deaths=1, dmg=(15, 80),
        scene_gap=(40, 90), store_view_p=0.1, purchase_p=0.03, quest_p=0.4, quest_fail_p=0.1,
        lifetime=(50, 400), cap=None, minor=False,
    ),
    "whale": dict(
        tier="whale", level=(25, 55), fights=(3, 7), death_p=0.12, max_deaths=2, dmg=(10, 70),
        scene_gap=(40, 100), store_view_p=0.3, purchase_p=0.12, quest_p=0.3, quest_fail_p=0.15,
        lifetime=(3000, 20000), cap=None, minor=False,
    ),
    "minor": dict(
        tier="F2P", level=(5, 25), fights=(2, 6), death_p=0.2, max_deaths=2, dmg=(5, 45),
        scene_gap=(45, 110), store_view_p=0.2, purchase_p=0.01, quest_p=0.3, quest_fail_p=0.3,
        lifetime=(0, 15), cap=None, minor=True,
    ),
    "capped": dict(
        tier="spender", level=(20, 45), fights=(3, 7), death_p=0.15, max_deaths=2, dmg=(10, 60),
        scene_gap=(40, 100), store_view_p=0.2, purchase_p=0.06, quest_p=0.3, quest_fail_p=0.2,
        lifetime=(300, 1500), cap=100.0, minor=False,
    ),
}

# Simulated roster per game (15 players each).
ROSTER_PER_GAME = {"casual": 6, "grinder": 4, "veteran": 2, "whale": 1, "minor": 1, "capped": 1}

# ---------------------------------------------------------------------------
# Dedicated demo players for the trigger buttons (DESIGN.md §7). The generator seeds and
# heartbeats their profiles but does NOT simulate play for them, so bursts are clean.
# Profiles are chosen to make each scenario unambiguous.
# ---------------------------------------------------------------------------

DEMO_PLAYERS = [
    # Boss wall: mid-spender level 32 in cinder_depths -> counter item vs cinder_wyrm.
    dict(player_id="demo-boss-wall", game_id="ember_throne", player_class="warrior", level=32, tier="spender",
         lifetime_spend=120.0, spend_30d=9.99, monthly_cap=None, is_minor=False, region="us-west",
         owned_skus=["healing_potion_10"]),
    # Gear gap: level 14 in core_reactor (min level 45), heavy damage + store views.
    dict(player_id="demo-gear-gap", game_id="starlane_arena", player_class="assault", level=14, tier="F2P",
         lifetime_spend=4.99, spend_30d=0.0, monthly_cap=None, is_minor=False, region="eu-west",
         owned_skus=[]),
    # Rage-quit risk: F2P, deaths -> failed quest -> logout -> free comeback gift/hint.
    dict(player_id="demo-rage-quit", game_id="tidal_rogue", player_class="harpooner", level=22, tier="F2P",
         lifetime_spend=0.0, spend_30d=0.0, monthly_cap=None, is_minor=False, region="jp",
         owned_skus=[]),
    # Same struggle, two profiles: identical game/class/level, F2P vs whale.
    dict(player_id="demo-f2p", game_id="ember_throne", player_class="mage", level=34, tier="F2P",
         lifetime_spend=0.0, spend_30d=0.0, monthly_cap=None, is_minor=False, region="us-east",
         owned_skus=[]),
    dict(player_id="demo-whale", game_id="ember_throne", player_class="mage", level=34, tier="whale",
         lifetime_spend=12500.0, spend_30d=640.0, monthly_cap=None, is_minor=False, region="us-east",
         owned_skus=["fire_resist_bundle", "heroic_gear_upgrade", "xp_boost_24h"]),
    # Guardrails: a minor and a capped player hit by the same boss wall.
    dict(player_id="demo-minor", game_id="starlane_arena", player_class="medic", level=33, tier="F2P",
         lifetime_spend=0.0, spend_30d=0.0, monthly_cap=None, is_minor=True, region="us-east",
         owned_skus=[]),
    dict(player_id="demo-capped", game_id="tidal_rogue", player_class="navigator", level=33, tier="spender",
         lifetime_spend=850.0, spend_30d=100.0, monthly_cap=100.0, is_minor=False, region="sea",
         owned_skus=["repair_kit_5"]),
    # Control: a veteran who dies twice -- should never reach the agent.
    dict(player_id="demo-veteran", game_id="ember_throne", player_class="ranger", level=55, tier="spender",
         lifetime_spend=300.0, spend_30d=15.0, monthly_cap=None, is_minor=False, region="kr",
         owned_skus=["heroic_gear_upgrade"]),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def zone_for_level(game_id, level):
    """Highest zone whose min_level the player has reached."""
    eligible = [z for z in GAMES[game_id]["zones"] if z["min_level"] <= level]
    return eligible[-1] if eligible else GAMES[game_id]["zones"][0]


def sku_price(game_id, sku):
    for s in GAMES[game_id]["skus"]:
        if s["sku"] == sku:
            return s["price"]
    raise KeyError(f"{game_id}: unknown sku {sku}")


def build_simulated_players(rng=None):
    """Create the simulated players: ROSTER_PER_GAME personas in every game.

    Returns a list of player dicts. Each has the profile fields (see the player_profiles table)
    plus `persona` and `simulate=True`. Profiles are mutable in-memory state; the generator
    upserts them whenever they change.
    """
    rng = rng or random
    players = []
    for game_id, game in GAMES.items():
        n = 0
        for persona_name, count in ROSTER_PER_GAME.items():
            persona = PERSONAS[persona_name]
            for _ in range(count):
                n += 1
                level = rng.randint(*persona["level"])
                lifetime = round(rng.uniform(*persona["lifetime"]), 2)
                cap = persona["cap"]
                spend_30d = 0.0
                if persona_name == "whale":
                    spend_30d = round(rng.uniform(200, 900), 2)
                elif cap is not None:
                    spend_30d = round(rng.uniform(0.6 * cap, 0.9 * cap), 2)  # near, not over, the cap
                elif lifetime > 0:
                    spend_30d = round(min(lifetime, rng.uniform(0, 20)), 2)
                players.append(dict(
                    player_id=f"{game_id[:3]}-{persona_name[:3]}-{n:02d}",
                    game_id=game_id,
                    player_class=rng.choice(game["classes"]),
                    level=level,
                    tier=persona["tier"],
                    lifetime_spend=lifetime,
                    spend_30d=spend_30d,
                    monthly_cap=cap,
                    is_minor=persona["minor"],
                    region=rng.choice(REGIONS),
                    owned_skus=[],
                    last_purchase_ts=None,
                    persona=persona_name,
                    simulate=True,
                ))
    return players


def build_demo_players():
    """Fixed demo players (not simulated; profile only)."""
    out = []
    for d in DEMO_PLAYERS:
        p = dict(d)
        p.setdefault("last_purchase_ts", None)
        p["persona"] = "demo"
        p["simulate"] = False
        out.append(p)
    return out
