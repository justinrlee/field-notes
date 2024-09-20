
Simple Java app that takes the following:
* CA Certificate (in PEM format)
* Client key + certificate (in PKCS12 format)

Will stand up an ephemeral server that trusts the CA certificate, and attempt to connect with the client certificate (and key)

Can be used to help validate the client certificate is trusted by the root CA and **can be used by a client to connect to something that trusts the CA**. Specifically, should identify issues like:
* Client cert not signed by CA
* Client cert is not a valid client certificate (due to extensions, etc.)

If there's a problem, it doesn't tell you what's wrong, just that something is wrong, although you can run in debug and examine the logs to see what might be going on.

Example successful usage:

```bash
java -jar mtls-1.0-SNAPSHOT.jar root.crt client.p12 changeme
Server started on port 38069
Successfully connected
```

Example unsuccesful usage:
```bash
java -jar mtls-1.0-SNAPSHOT.jar root.crt client.p12 changeme
Server started on port 30439
java.net.SocketException: Broken pipe
	at java.base/sun.nio.ch.NioSocketImpl.implWrite(NioSocketImpl.java:425)
	at java.base/sun.nio.ch.NioSocketImpl.write(NioSocketImpl.java:445)
	at java.base/sun.nio.ch.NioSocketImpl$2.write(NioSocketImpl.java:831)
	at java.base/java.net.Socket$SocketOutputStream.write(Socket.java:1035)
	at java.base/sun.security.ssl.SSLSocketOutputRecord.flush(SSLSocketOutputRecord.java:271)
	at java.base/sun.security.ssl.HandshakeOutStream.flush(HandshakeOutStream.java:89)
	at java.base/sun.security.ssl.Finished$T13FinishedProducer.onProduceFinished(Finished.java:693)
	at java.base/sun.security.ssl.Finished$T13FinishedProducer.produce(Finished.java:672)
	at java.base/sun.security.ssl.SSLHandshake.produce(SSLHandshake.java:440)
	at java.base/sun.security.ssl.Finished$T13FinishedConsumer.onConsumeFinished(Finished.java:1030)
	at java.base/sun.security.ssl.Finished$T13FinishedConsumer.consume(Finished.java:893)
	at java.base/sun.security.ssl.SSLHandshake.consume(SSLHandshake.java:396)
	at java.base/sun.security.ssl.HandshakeContext.dispatch(HandshakeContext.java:480)
	at java.base/sun.security.ssl.HandshakeContext.dispatch(HandshakeContext.java:458)
	at java.base/sun.security.ssl.TransportContext.dispatch(TransportContext.java:201)
	at java.base/sun.security.ssl.SSLTransport.decode(SSLTransport.java:172)
	at java.base/sun.security.ssl.SSLSocketImpl.decode(SSLSocketImpl.java:1510)
	at java.base/sun.security.ssl.SSLSocketImpl.readHandshakeRecord(SSLSocketImpl.java:1425)
	at java.base/sun.security.ssl.SSLSocketImpl.startHandshake(SSLSocketImpl.java:455)
	at java.base/sun.security.ssl.SSLSocketImpl.ensureNegotiated(SSLSocketImpl.java:925)
	at java.base/sun.security.ssl.SSLSocketImpl$AppOutputStream.write(SSLSocketImpl.java:1295)
	at java.base/sun.security.ssl.SSLSocketImpl$AppOutputStream.write(SSLSocketImpl.java:1267)
	at io.justinrlee.MTLSTest.testSSLConnection(MTLSTest.java:116)
	at io.justinrlee.MTLSTest.main(MTLSTest.java:234)
```


TODO:
* Swap server to NIO socket server (rather than HTTPS)
* Update client
* Figure out how to turn on server-side logging
* Better argument handling
* 