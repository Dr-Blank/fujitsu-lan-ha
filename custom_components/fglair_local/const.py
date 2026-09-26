"""Constants for Fujitsu FGLair Local."""

DOMAIN = "fglair_local"

CONF_DSN = "dsn"
CONF_LANIP_KEY = "lanip_key"
CONF_LANIP_KEY_ID = "lanip_key_id"
CONF_CALLBACK_HOST = "callback_host"
CONF_CALLBACK_PORT = "callback_port"

# Public FGLair mobile-app credentials: they identify the app, not the user.
FGLAIR_APPS: dict[str, tuple[str, str]] = {
    "us": ("CJIOSP-id", "CJIOSP-Vb8MQL_lFiYQ7DKjN0eCFXznKZE"),
    "eu": ("FGLair-eu-id", "FGLair-eu-gpFbVBRoiJ8E3QWJ-QRULLL3j3U"),
    "cn": ("FGLairField-cn-id", "FGLairField-cn-zezg7Y60YpAvy3HPwxvWLnd4Oh4"),
}
