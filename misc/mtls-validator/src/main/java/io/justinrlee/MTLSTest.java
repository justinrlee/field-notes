package io.justinrlee;

import java.io.*;
import java.security.*;
import java.security.KeyStore;

import java.math.BigInteger;
import java.util.Date;
import java.security.cert.X509Certificate;
import javax.security.auth.x500.X500Principal;

import java.util.concurrent.ThreadLocalRandom;

import java.security.cert.CertificateFactory;

import org.bouncycastle.asn1.ASN1Encodable;
import org.bouncycastle.asn1.DERSequence;
// import org.bouncycastle.asn1.pkcs.PrivateKeyInfo;
import org.bouncycastle.asn1.x509.BasicConstraints;
import org.bouncycastle.asn1.x509.ExtendedKeyUsage;
import org.bouncycastle.asn1.x509.Extension;
import org.bouncycastle.asn1.x509.GeneralName;
import org.bouncycastle.asn1.x509.KeyPurposeId;
import org.bouncycastle.asn1.x509.KeyUsage;
// import org.bouncycastle.cert.X509CertificateHolder;
import org.bouncycastle.cert.X509v3CertificateBuilder;
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder;
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.operator.ContentSigner;
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder;

// import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpsServer;


// import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import java.net.URL;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.KeyManagerFactory;
import java.net.InetSocketAddress;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.Option;
import org.apache.commons.cli.Options;
import org.apache.commons.cli.DefaultParser;

class MTLSTest {

    // Build an SSLContext with a keyStore and trustStore
    static SSLContext buildSSLContext(
            KeyStore keyStore,
            char[] keystorePass,
            KeyStore trustStore
    ) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keyStore, keystorePass);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trustStore);

        SSLContext sslContext = SSLContext.getInstance("TLS");
        sslContext.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);

        return sslContext;
    }

    static HttpsServer buildHttpsServer(
            SSLContext sslContext,
            int port
    ) throws Exception {
        HttpsServer server = HttpsServer.create(new InetSocketAddress(port), 0);
        server.setHttpsConfigurator(new com.sun.net.httpserver.HttpsConfigurator(sslContext) {
            @Override
            public void configure(com.sun.net.httpserver.HttpsParameters params) {
                SSLParameters sslParams = sslContext.getDefaultSSLParameters();

                sslParams.setNeedClientAuth(true); // Require client auth for mTLS

                params.setSSLParameters(sslParams);
            }
        });

        // Create a simple handler
        server.createContext("/", new HttpHandler() {
            @Override
            public void handle(HttpExchange exchange) throws IOException {
                String response = "Success";
                exchange.sendResponseHeaders(200, response.length());
                OutputStream os = exchange.getResponseBody();
                os.write(response.getBytes());
                os.close();
            }
        });

        return server;
    }

    static void testSSLConnection(SSLContext clientSSLContext, int port) throws Exception {
            SSLSocketFactory sslSocketFactory = clientSSLContext.getSocketFactory();
            SSLSocket sslSocket = (SSLSocket) sslSocketFactory.createSocket("localhost", port);

            InputStream in = sslSocket.getInputStream();
            OutputStream out = sslSocket.getOutputStream();

            // Write a test byte to get a reaction :)
            out.write(1);

            while (in.available() > 0) {
                System.out.print(in.read());
            }
            System.out.println("Successfully connected");
    }

    // Create a private key and server certificate with CN=localhost
    // Returns a keystore with two entries:
    // * server certificate as a trusted CA (for use by client)
    // * server certificate with private key (for use by server)
    static KeyStore generateInternalKeyStore(char[] storePass) throws Exception {
        Provider bcProvider = new BouncyCastleProvider();
        Security.addProvider(bcProvider);

        KeyPairGenerator keyGen = KeyPairGenerator.getInstance("RSA");
        keyGen.initialize(2048);
        KeyPair keyPair = keyGen.generateKeyPair();
        
        X500Principal subject = new X500Principal("CN=localhost");
        X500Principal signedByPrincipal = subject;

        long notBefore = System.currentTimeMillis();
        long notAfter = notBefore + (1000L * 3600L * 24 * 365);
        
        ASN1Encodable[] encodableAltNames = new ASN1Encodable[]{new GeneralName(GeneralName.dNSName, "localhost")};
        KeyPurposeId[] purposes = new KeyPurposeId[]{KeyPurposeId.id_kp_serverAuth, KeyPurposeId.id_kp_clientAuth};

        X509v3CertificateBuilder certBuilder = new JcaX509v3CertificateBuilder(
            signedByPrincipal,
            BigInteger.ONE,
            new Date(notBefore),
            new Date(notAfter),
            subject,
            keyPair.getPublic()
        );
        
        certBuilder.addExtension(Extension.basicConstraints, true, new BasicConstraints(true));
        certBuilder.addExtension(Extension.keyUsage, true, new KeyUsage(KeyUsage.digitalSignature + KeyUsage.keyEncipherment));
        certBuilder.addExtension(Extension.extendedKeyUsage, false, new ExtendedKeyUsage(purposes));
        certBuilder.addExtension(Extension.subjectAlternativeName, false, new DERSequence(encodableAltNames));

        final ContentSigner contentSigner = new JcaContentSignerBuilder(("SHA256withRSA")).build(keyPair.getPrivate());

        X509Certificate certificate = new JcaX509CertificateConverter().setProvider(bcProvider).getCertificate(certBuilder.build(contentSigner));

        // Create a KeyStore and store the certificate
        KeyStore keyStore = KeyStore.getInstance("PKCS12");
        keyStore.load(null, null); // Initialize empty keystore
        keyStore.setKeyEntry("localhost", keyPair.getPrivate(), storePass, new X509Certificate[]{certificate});
        keyStore.setCertificateEntry("ca", certificate);

        return keyStore;
    }

    public static void main(String[] args) {
        HttpsServer server = null;
        KeyStore clientKeyStore;
        KeyStore customerTrustStore;
        KeyStore internalKeystore;

        try {
            if (args.length < 3) {
                System.out.println("Usage: java -jar mtls-1.0-SNAPSHOT.jar <root-ca> <truststore> <truststore-password>");
                System.out.println("java -jar mtls-1.0-SNAPSHOT.jar /home/ubuntu/custom-root.crt /home/ubuntu/client.p12 changeme");
                System.out.println("For debug, add -Djavax.net.debug=ssl:handshake:");
                System.out.println("java -Djavax.net.debug=ssl:handshake -jar mtls-1.0-SNAPSHOT.jar /home/ubuntu/custom-root.crt /home/ubuntu/client.p12 changeme");
                System.exit(1);
            }
            String customerCertificateAuthorityFile = args[0];
            String clientKeyStoreFile = args[1];
            char[] clientKeyStorePass = args[2].toCharArray();

            // TODO: Make sure to populate these before actually using them
            String serverTrustStoreFile;
            char[] serverTrustStorePass;

            int port = ThreadLocalRandom.current().nextInt(30000, 40000);

            clientKeyStore = KeyStore.getInstance("PKCS12");
            clientKeyStore.load(new FileInputStream(clientKeyStoreFile), clientKeyStorePass);

            customerTrustStore = KeyStore.getInstance("PKCS12");

            // Placeholder; eventually support providing truststore as PKCS12 file
            if (true) {
                customerTrustStore.load(null, null);
                customerTrustStore.setCertificateEntry(
                    "ca", 
                    CertificateFactory.getInstance("X509").generateCertificate(new FileInputStream(customerCertificateAuthorityFile))
                );
            } else {
                // Make sure to populate these before actually using them; these are current null
                customerTrustStore.load(new FileInputStream(serverTrustStoreFile), serverTrustStorePass);
            }  

            char[] internalKeyStorePass = "changeme".toCharArray();
            internalKeystore = generateInternalKeyStore(internalKeyStorePass);

            // Server listens with internal SS cert, trusts user-provided truststore
            SSLContext serverSSLContext = buildSSLContext(
                internalKeystore,
                internalKeyStorePass,
                customerTrustStore
            );
            server = buildHttpsServer(serverSSLContext, port);
            server.start();
            System.out.println("Server started on port " + Integer.toString(port));

            // Server connects with user-provided cert, trusts internal SS cert
            SSLContext clientSSLContext = buildSSLContext(
                clientKeyStore,
                clientKeyStorePass,
                internalKeystore
            );
            Thread.sleep(2);
            
            testSSLConnection(clientSSLContext, port);
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            server.stop(1);
        }
    }
}