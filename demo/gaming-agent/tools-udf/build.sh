#!/usr/bin/env bash
# Build target/gaming-tools.jar with a LOCAL JDK (17 or 21) + Maven. The pom compiles for Java 11
# (--release 11), which is what Confluent Cloud Flink UDFs need, regardless of the JDK used here.
# The JAR is committed to the repo and uploaded by Terraform (confluent_flink_artifact); only rebuild
# when the Java sources change.
set -euo pipefail

cd "$(dirname "$0")"

command -v mvn >/dev/null || { echo "mvn not found (brew install maven)"; exit 1; }

# Prefer JDK 21, then 17, over whatever Maven's default JDK is (the very newest JDKs are untested here).
# Override by exporting JAVA_HOME yourself. (macOS: /usr/libexec/java_home lists installed JDKs.)
if [ -z "${JAVA_HOME:-}" ] && [ -x /usr/libexec/java_home ]; then
  for v in 21 17; do
    if jh="$(/usr/libexec/java_home -v "$v" 2>/dev/null)"; then export JAVA_HOME="$jh"; break; fi
  done
fi
echo "Using:"; mvn -v | head -3

mvn -q -DskipTests clean package

echo "Built: $(pwd)/target/gaming-tools.jar"
unzip -l target/gaming-tools.jar | grep -E 'io/confluent/gamingdemo/.*\.class'
