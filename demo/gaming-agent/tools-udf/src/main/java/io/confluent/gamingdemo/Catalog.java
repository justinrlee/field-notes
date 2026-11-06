package io.confluent.gamingdemo;

import java.util.List;
import java.util.Map;

/**
 * Static mock catalog shared by the tools. Ids must match producer/gamedata.py.
 */
final class Catalog {
    private Catalog() {}

    static final class Sku {
        final String sku;
        final String name;
        final String category; // counter | gear | consumable | boost
        final double price;
        final List<String> counters; // boss ids this SKU is especially useful against

        Sku(String sku, String name, String category, double price, List<String> counters) {
            this.sku = sku;
            this.name = name;
            this.category = category;
            this.price = price;
            this.counters = counters;
        }
    }

    static final class Zone {
        final String id;
        final int minLevel;
        final String boss;

        Zone(String id, int minLevel, String boss) {
            this.id = id;
            this.minLevel = minLevel;
            this.boss = boss;
        }
    }

    static final Map<String, List<Zone>> ZONES = Map.of(
        "ember_throne", List.of(
            new Zone("ashen_keep", 1, "ash_brute"),
            new Zone("frostfall_pass", 15, "ice_golem"),
            new Zone("cinder_depths", 30, "cinder_wyrm"),
            new Zone("obsidian_citadel", 45, "void_regent")),
        "starlane_arena", List.of(
            new Zone("dock_9", 1, "drone_warden"),
            new Zone("nebula_ring", 15, "storm_leviathan"),
            new Zone("debris_field", 30, "scrap_tyrant"),
            new Zone("core_reactor", 45, "reactor_titan")),
        "tidal_rogue", List.of(
            new Zone("shallows", 1, "brine_crab_king"),
            new Zone("kelp_maze", 15, "hydra_mother"),
            new Zone("sunken_fleet", 30, "ghost_admiral"),
            new Zone("abyssal_trench", 45, "maw_of_the_deep")));

    static final Map<String, List<Sku>> SKUS = Map.of(
        "ember_throne", List.of(
            new Sku("frost_ward_bundle", "Frost Ward Bundle", "counter", 4.99, List.of("ice_golem")),
            new Sku("fire_resist_bundle", "Fire Resist Bundle", "counter", 4.99, List.of("cinder_wyrm", "ash_brute")),
            new Sku("void_shield_pack", "Void Shield Pack", "counter", 6.99, List.of("void_regent")),
            new Sku("healing_potion_10", "Healing Potion x10", "consumable", 1.99, List.of()),
            new Sku("heroic_gear_upgrade", "Heroic Gear Upgrade", "gear", 9.99, List.of()),
            new Sku("xp_boost_24h", "24h XP Boost", "boost", 2.99, List.of())),
        "starlane_arena", List.of(
            new Sku("ion_shield_pack", "Ion Shield Pack", "counter", 3.99, List.of("storm_leviathan")),
            new Sku("emp_grenade_bundle", "EMP Grenade Bundle", "counter", 4.99, List.of("drone_warden", "scrap_tyrant")),
            new Sku("reactor_suit_mk2", "Reactor Suit Mk II", "gear", 11.99, List.of("reactor_titan")),
            new Sku("medkit_pack_10", "Medkit Pack x10", "consumable", 1.99, List.of()),
            new Sku("weapon_mod_kit", "Weapon Mod Kit", "gear", 7.99, List.of()),
            new Sku("battle_pass_boost", "Battle Pass Boost", "boost", 4.99, List.of())),
        "tidal_rogue", List.of(
            new Sku("venom_antidote_bundle", "Venom Antidote Bundle", "counter", 3.99, List.of("hydra_mother")),
            new Sku("spectral_cannon_pack", "Spectral Cannon Pack", "counter", 5.99, List.of("ghost_admiral")),
            new Sku("pressure_hull_upgrade", "Pressure Hull Upgrade", "gear", 9.99, List.of("maw_of_the_deep")),
            new Sku("repair_kit_5", "Repair Kit x5", "consumable", 1.49, List.of()),
            new Sku("lucky_loot_crate", "Lucky Loot Crate", "boost", 2.99, List.of()),
            new Sku("rum_ration_bundle", "Rum Ration Bundle", "consumable", 0.99, List.of())));

    /** Free, never-sold items the agent can give instead of (or alongside) a paid offer. */
    static final String FREE_HINT = "free_boss_hint";
    static final String FREE_GIFT = "free_comeback_gift";

    /** Largest discount the demo allows on a paid SKU. */
    static final int MAX_DISCOUNT_PCT = 30;

    static Sku findSku(String sku) {
        for (List<Sku> list : SKUS.values()) {
            for (Sku s : list) {
                if (s.sku.equals(sku)) {
                    return s;
                }
            }
        }
        return null;
    }

    static Zone findZone(String gameId, String zoneId) {
        List<Zone> zones = ZONES.get(gameId);
        if (zones != null) {
            for (Zone z : zones) {
                if (z.id.equals(zoneId)) {
                    return z;
                }
            }
        }
        return null;
    }

    /** Minimal JSON string escaping for the values we emit. */
    static String q(String s) {
        if (s == null) {
            return "null";
        }
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
