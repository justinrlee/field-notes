package io.justinrlee.kafka.flink.config;

import org.apache.flink.api.java.utils.ParameterTool;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import java.io.File;
import java.io.FileInputStream;

public class ConfigurationManager {
    private static final String DEFAULT_PROPERTIES_FILE = "application.properties";
    private final Properties properties;

    public ConfigurationManager(String[] args) throws IOException {
        properties = new Properties();
        
        // System.out.println("Default properties file: " + DEFAULT_PROPERTIES_FILE);
        File file = new File(DEFAULT_PROPERTIES_FILE);

        if (file.exists() && file.isFile()) {
            try (InputStream input = new FileInputStream(file)) {
                properties.load(input);
                // System.out.println("Loaded default properties: " + properties);
            }
        }

        // Override with any properties passed via command line
        ParameterTool parameters = ParameterTool.fromArgs(args);
        String externalPropertiesFile = parameters.get("properties.file", "");

        // System.out.println("External properties file: " + externalPropertiesFile);
        file = new File(externalPropertiesFile);

        if (file.exists() && file.isFile()) {
            try (InputStream input = new FileInputStream(file)) {
                properties.load(input);
                // System.out.println("Loaded external properties: " + properties);
            }
        }

        properties.putAll(parameters.toMap());

        System.out.println("Properties: " + properties);
    }

    public String getProperty(String key) {
        return properties.getProperty(key);
    }

    public String getProperty(String key, String defaultValue) {
        return properties.getProperty(key, defaultValue);
    }

    public Properties getProperties() {
        return new Properties(properties);
    }
} 