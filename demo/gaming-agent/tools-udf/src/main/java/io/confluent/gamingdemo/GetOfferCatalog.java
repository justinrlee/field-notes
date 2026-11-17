package io.confluent.gamingdemo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.apache.flink.table.functions.ScalarFunction;

/**
 * Candidate offers for a struggling player, ranked by relevance. Mock tool: the catalog is built
 * into the JAR. Returns a JSON string.
 *
 * <p>Relevance: {@code counters_source} (SKU counters the boss that is killing the player), then
 * {@code gear_upgrade_for_level_gap} (gear SKUs when the player is >= 10 levels below the zone), then
 * {@code general}. Free options are always listed and are never sold.
 */
public class GetOfferCatalog extends ScalarFunction {
    public String eval(String gameId, String playerClass, Integer level, String zoneId, String sourceId) {
        List<Catalog.Sku> skus = Catalog.SKUS.get(gameId);
        if (skus == null) {
            return "{\"error\":" + Catalog.q("unknown game_id " + gameId) + "}";
        }
        int lvl = level == null ? 0 : level;
        Catalog.Zone zone = Catalog.findZone(gameId, zoneId);
        int levelGap = zone == null ? 0 : Math.max(zone.minLevel - lvl, 0);

        List<String> counters = new ArrayList<>();
        List<String> gear = new ArrayList<>();
        List<String> general = new ArrayList<>();
        for (Catalog.Sku s : skus) {
            if (sourceId != null && s.counters.contains(sourceId)) {
                counters.add(entry(s, "counters_source"));
            } else if ("gear".equals(s.category) && levelGap >= 10) {
                gear.add(entry(s, "gear_upgrade_for_level_gap"));
            } else {
                general.add(entry(s, "general"));
            }
        }
        List<String> all = new ArrayList<>(counters);
        all.addAll(gear);
        all.addAll(general);

        StringBuilder sb = new StringBuilder();
        sb.append("{\"game_id\":").append(Catalog.q(gameId));
        sb.append(",\"player_class\":").append(Catalog.q(playerClass));
        sb.append(",\"player_level\":").append(lvl);
        sb.append(",\"zone_id\":").append(Catalog.q(zoneId));
        sb.append(",\"zone_min_level\":").append(zone == null ? "null" : String.valueOf(zone.minLevel));
        sb.append(",\"level_gap\":").append(levelGap);
        sb.append(",\"source_id\":").append(Catalog.q(sourceId));
        sb.append(",\"max_discount_pct\":").append(Catalog.MAX_DISCOUNT_PCT);
        sb.append(",\"paid_skus\":[").append(String.join(",", all)).append("]");
        sb.append(",\"free_options\":[")
          .append("{\"sku\":").append(Catalog.q(Catalog.FREE_HINT))
          .append(",\"kind\":\"hint\",\"description\":").append(Catalog.q("A tip on how to beat " + sourceId + " (free)")).append("}")
          .append(",{\"sku\":").append(Catalog.q(Catalog.FREE_GIFT))
          .append(",\"kind\":\"gift\",\"description\":").append(Catalog.q("A small comeback gift pack (free)")).append("}")
          .append("]}");
        return sb.toString();
    }

    private static String entry(Catalog.Sku s, String relevance) {
        return String.format(Locale.ROOT,
            "{\"sku\":%s,\"name\":%s,\"category\":%s,\"price\":%.2f,\"relevance\":%s}",
            Catalog.q(s.sku), Catalog.q(s.name), Catalog.q(s.category), s.price, Catalog.q(relevance));
    }
}
