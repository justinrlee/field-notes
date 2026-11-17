package io.confluent.gamingdemo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.apache.flink.table.functions.ScalarFunction;

/**
 * The monetization guardrail. Decides whether a PAID offer is allowed for a player.
 *
 * <p>Mock tool: a UDF has no state and no database access, so the agent passes the profile values it
 * was given in the prompt, as strings (LLM-friendly: "true"/"false", a number, or "none"). The cooldown
 * is a proxy: a purchase in the last 15 minutes. Returns a JSON string.
 */
public class CheckOfferEligibility extends ScalarFunction {
    private static final long COOLDOWN_MS = 15L * 60L * 1000L;

    // Time-dependent (cooldown), so not a pure function.
    @Override
    public boolean isDeterministic() {
        return false;
    }

    public String eval(String playerId, String isMinor, String spend30d, String monthlyCap, String lastPurchaseTs) {
        List<String> reasons = new ArrayList<>();

        boolean minor = isMinor != null && isMinor.trim().equalsIgnoreCase("true");
        if (minor) {
            reasons.add("player_is_minor");
        }

        Double spend = parseNumber(spend30d);
        Double cap = parseNumber(monthlyCap);
        Double remaining = null;
        if (cap != null) {
            remaining = Math.max(cap - (spend == null ? 0.0 : spend), 0.0);
            if (remaining <= 0.0) {
                reasons.add("monthly_cap_reached");
            }
        }

        boolean cooldown = false;
        Double last = parseNumber(lastPurchaseTs);
        if (last != null && System.currentTimeMillis() - last.longValue() < COOLDOWN_MS) {
            cooldown = true;
            reasons.add("recent_purchase_cooldown");
        }

        boolean allowed = reasons.isEmpty();
        StringBuilder sb = new StringBuilder();
        sb.append("{\"player_id\":").append(Catalog.q(playerId));
        sb.append(",\"paid_offers_allowed\":").append(allowed);
        sb.append(",\"reasons\":[");
        for (int i = 0; i < reasons.size(); i++) {
            sb.append(i == 0 ? "" : ",").append(Catalog.q(reasons.get(i)));
        }
        sb.append("]");
        sb.append(",\"cooldown_active\":").append(cooldown);
        sb.append(",\"remaining_monthly_budget\":")
          .append(remaining == null ? "null" : String.format(Locale.ROOT, "%.2f", remaining));
        sb.append("}");
        return sb.toString();
    }

    /** Parses a number; returns null for null/blank/"none"/"null"/"never"/unparseable. */
    private static Double parseNumber(String s) {
        if (s == null) {
            return null;
        }
        String t = s.trim();
        if (t.isEmpty() || t.equalsIgnoreCase("none") || t.equalsIgnoreCase("null") || t.equalsIgnoreCase("never")) {
            return null;
        }
        try {
            return Double.valueOf(t);
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
