
---
# Overview

*This was originally written for github.com/mesosphere/field-notes*

This document is primarily for reference/training purposes.  A lot of the items here should not be used in production without modification.  For example, it leaves auth tokens in your command history and on your filesystem, so make sure you clean up after you're done.

This document is broken into two sections:
0. Intro to certificates (in the context of DC/OS)

1. A section regarding configuring DC/OS with certificates, including the following (**DC/OS Enterprise Only**)
    <!-- a. Using OpenSSL, creating a self-signed CA certificate and key
    b. Using OpenSSL, creating an intermediate CA, signed by the above self-signed CA certificate
    c. Configuring DC/OS EE 1.10.0 to use the intermediate CA certificate generated above -->
    a. Using the DC/OS EE CA APIs to generate and sign certificates

2. A section regarding configuring DC/OS to trust certificates, including:

    a. Create a local Docker repo using a self signed certificate

    b. Configuring the Docker daemon within DC/OS to trust certificates

    c. Configuring the UCR fetcher to trust certificates

    d. Configuring the Docker daemon with Docker creds

    e. Configuring the UCR fetcher to use Docker creds

Section 1 and 2 are only slightly related, in that:
* They both deal with certificates
* If you're running a private Docker registry, you can use the DC/OS CA to sign the certificates
* By default, the Mesos fetcher on DC/OS agents will trust certificates signed by the DC/OS CA.  
    * The Docker daemon will not trust them by default.
    * Public agents may not work correctly at the moment (this is being addressed)

There will be a follow-on document walking through configuring DC/OS Marathon-LB or Edge-LB, and 

# Intro to Certificates

This is a non-complete introduction to certificates - you can find better guides all over the Internet.  It has some very basic concepts that are helpful for understanding DC/OS behavior related to certificates.  It is also hugely simplified and leaves out symmetric keys and key negotation and a lot of other things.  A lot of the terminology is wrong.  I'm sorry.

## Relevant Concepts / Files
There are basically three files that are relevant to certificates:

* Certificates - these are generally *public* files, and are used to indicate that "I am server X".  When you connect with a server that has a certificate, the certificate is the file that is presented to the client to indicate who they are.  
    * Certificates can either be self-signed, or signed by somebody else (another trusted entity).
    * In the context of DC/OS, Enterprise DC/OS has a CA which can be used to sign certificates.  In order to fully use this functionality, your clients should be configured to trust the DC/OS CA (more on this later).
    * Certificates often have additional data embedded in them, such as owner, issuer, and lots of other metadata.
    * Certificates can indicate that they are valid for multiple entities.  For example, a server can say "I am both server X and server X.com".

* Keys - these are often sensitive files, and should be kept *private*.  They usually accompany a given certificate, but are *not* sent along with the certificate.  Generally, they are used to prove that "I'm the owner of this key".  Don't worry about the full technical details of this, aside from the fact that the key sits on the server(s) that present the certificate to clients, and is used to prove to the clients that the server is actually the owner of the certificate, but is never directly sent to the client.
    * Keys can be generated in a variety of ways.  You can use the openssl tool, or you can use DC/OS to sign certificates (if using the Enterprise version of DC/OS)
    * A certitificate is actually a public key with additional metadata.

* Certificate Signing Requests - these are an intermediate file that can be used to request a certificate, usually by somebody with a key.  Think: "Hi Verisign, I have key A, can you sign a certificate and give it to me so that I can use it to prove that I am server X"
    * EE DC/OS can process CSRs and "sign" them, and send back a certificate (more on this later).

All three file types look roughly like this, with 'XYZ' replaced with the type of content ('CERTIFICATE', 'PRIVATE KEY', or 'CERTIFICATE REQUEST' or something else), and a varying length for the body.  

```
-----BEGIN XYZ-----
MIIDVzCCAj+gAwIBAgIJANUrJ2G0RBb6MA0GCSqGSIb3DQEBCwUAMEIxCzAJBgNV
... (More lines of 64 characters) ...
qGDqzKEm14AwHwYDVR0jBBgwFoAUOPZF1A+6vegzZpBFqGDqzKEm14AwDAYDVR0T
hjCYICUonpLrQItoR+CXE+tPGCQSxjJ8SU4iGJLRL9sDKc/R/AaCoN+Cbw==
-----END XYZ-----
```

In general, this file format is called a 'PEM' file.  Also, extension doesn't always matter, but is often useful for specifying what type of pem file it is.  So you'll see things like:
* .pem used interchangeably for all
* .cert or .crt used for pem files that hold a certificate (crt often used for server certificates, cert often used for client certificates)
* .key used for pem files that hold a key
* .csr used for pem files that hold a certificate signing request

Additionally, a pem file can contain multiple pem entries concatenated together (for example, a matching certificate and key, or a list of intermediate certificates).

For this document, I will use `filename.crt.pem` to indicate a pem file holding a certificate, and `filename.key.pem` to indicate a pem file holding a key.  **This is not standard**.

## Trust

If I am a client trying to connect to server X using SSL/TLS, then all three of the following must occur:
* Server x must present a certificate that says "I am Server X", that matches the name of the server I'm trying to connect to (case insensitive)
    * If I'm trying to connect to server X.com, and the server says "I am server X", then this doesn't work.  It must be an exact match.
    * If I'm trying to connect to server A.X.com, and the server says "I am server *.X.com", then this does work (wildcard certificate)
    * If I'm trying to connect to server A.X.com, which resolves in DNS to 10.10.0.200, and the server says "I am server 10.10.0.200", then this will not work, because I'm trying to connect to the DNS name, not to the IP.  My client doesn't know that A.X.com = 10.10.0.200 (DNS resolution is outside of the client). 
    * If I'm trying to connect to server 10.10.0.200, which is the DNS resolution for A.X.com, and the server says "I am server A.X.com", then this will not work, because I'm trying to connect to the IP address, not the DNS name.  My client doesn't know that A.X.com = 10.10.0.200 (DNS resolution is outside of the client). 
* Server x must have a key that matches that certificate
    * There's some magic that goes on in the back end to handle the verification of this, that you usually don't have to worry too much about assuming you're using modern libraries.
* I must either trust the bearer certificate, or somebody else who has signed that certificate
    * I can either trust the certificate directly, or I can trust the entity that signed the certificate, or I can trust an entity that signed an intermediate certificate that was then used to sign the certificate (this is called a certificate chain, and can be relatively indefinitely long).

(Alternately, you can specify to your client not to verify trust.  This is often done with the `-k` flag in curl, or adding an exception in your browser)

## Example
If you navigate to https://gist.github.com, and inspect the certificate in your browser (different browsers have different ways of doing this), you'll see the following certificates:
* DigiCert High Assurance EV Root CA - this is inherently trusted by most computers, in your computer's trust store (all computers have a list of root CA certificates that they inherently trust)
* DigiCert SHA2 High Assurance Server CA - this certificate was signed by the Root CA (which we trust), so we trust it.
* *.github.com - this certificate was signed by the "High Assurance Server CA" (which we now trust), so we trust it.

Also, because gist.github.com matches *.github.com, we're good on the first condition.