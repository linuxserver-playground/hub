# Ldap-auth

![Ldap-auth](https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/ldap-auth-logo.png)

[Ldap-auth](https://github.com/nginxinc/nginx-ldap-auth) software is for authenticating users who request protected resources from servers proxied by nginx. It includes a daemon (ldap-auth) that communicates with an authentication server, and a webserver daemon that generates an authentication cookie based on the user’s credentials. The daemons are written in Python for use with a Lightweight Directory Access Protocol (LDAP) authentication server (OpenLDAP or Microsoft Windows Active Directory 2003 and 2012).

## Application setup

- This container itself does not have any settings and it relies on the pertinent information passed through in http headers of incoming requests. Make sure that your webserver is set up with the right config.
- Here's a sample config: [nginx-ldap-auth.conf](https://github.com/nginxinc/nginx-ldap-auth/blob/master/nginx-ldap-auth.conf).
- Unlike the upstream project, this image encodes the cookie information with fernet, using a randomly generated key during container creation (or optionally user defined).
- Also unlike the upstream project, this image serves the login page at `/ldaplogin` (as well as `/login`) to prevent clashes with reverse proxied apps that may also use `/login` for their internal auth.

Image: `ghcr.io/linuxserver-playground/ldap-auth:latest` ([https://github.com/linuxserver-playground/docker-ldap-auth](https://github.com/linuxserver-playground/docker-ldap-auth))
