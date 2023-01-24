"""Configuration d'administration et maintenance.

Pour définir les proxies HTTPS et HTTP :

    >>> UserConfig.set_proxy('host:port')

Pour définir le proxy pour un protocol donné :

    >>> UserConfig.set_proxy('host:port', protocol='https')

Pour utiliser les paramètres définis dynamiquement dans les requêtes:

    >>> import requests
    >>> requests.get('http://domain/some_http_request', **REQUESTS_CONFIG)

"""

LOGO_BASE = 'https://registre.data.developpement-durable.gouv.fr/logos'
DEFAULT_LOGO = 'https://registre.data.developpement-durable.gouv.fr/logos/administration-centrale-ou-ministere.png'

ECOSPHERES_ENV = [
    {
        'name': 'prod',
        'title': 'production',
        'url': 'https://data.developpement-durable.gouv.fr'
    },
    {
        'name': 'preprod',
        'title': 'pré-production',
        'url': 'https://preprod.data.developpement-durable.gouv.fr',
        'verify': False
    },
    {
        'name': 'dev',
        'title': 'développement (distant)',
        'url': 'https://dev.data.developpement-durable.gouv.fr',
        'verify': False
    },
    {
        'name': 'local',
        'title': 'développement (local)',
        'url': 'http://localhost:5000',
        'verify': False
    }
]
"""Définition des environnements disponibles.

Il est nécessaire d'ajouter une clé ``'verify'`` valant ``False`` pour les
environnement avec des certificats SSL auto-signés. Cela aura pour effet
d'inhiber la vérification des certificats lors de l'utilisation de l'API
sur ces environnements.

Pour utiliser l'API pour les opérations de maintenance sur l'environnement
considéré, il faudra copier un jeton d'API valide dans un fichier ``.txt``
portant le même nom ``name`` que l'environnement et placé dans ``maintenance/token``.

"""

class UserConfig:
    """Interface pour la mise à jour dynamique de la configuration.

    À date, permet notamment de définir le proxy pour les
    requêtes HTTP/HTTPS.

    """
    _REQUESTS_CONFIG = {}

    @classmethod
    def http_proxy(cls):
        """Renvoie le proxy défini pour les requêtes HTTP.
        
        Returns
        -------
        str or None

        """
        if 'proxies' in cls._REQUESTS_CONFIG:
            return cls._REQUESTS_CONFIG['proxies'].get('http')

    @classmethod
    def https_proxy(cls):
        """Renvoie le proxy défini pour les requêtes HTTPS.
        
        Returns
        -------
        str or None

        """
        if 'proxies' in cls._REQUESTS_CONFIG:
            return cls._REQUESTS_CONFIG['proxies'].get('https')
    
    @classmethod
    def set_proxy(cls, value, protocol=None):
        """Définit le proxy pour les requêtes HTTP et/ou HTTPS.
        
        Parameters
        ----------
        value : str
            Le proxy, avec la syntaxe ``host:port``.
        protocol: {None, 'http', 'https'}, optional
            Si défini, le proxy ne sera mis à jour que pour le
            protocole considéré.
        
        """
        protocols = [
            p for p in ('http', 'https') if not protocol or p == protocol
        ]
        for p in protocols:
            if not 'proxies' in cls._REQUESTS_CONFIG:
                if not value:
                    return
                cls._REQUESTS_CONFIG['proxies'] = {p: value}
            else:
                if value:
                    cls._REQUESTS_CONFIG['proxies'].update({p: value})
                elif p in cls._REQUESTS_CONFIG['proxies']:
                    del cls._REQUESTS_CONFIG['proxies'][p]
                    if not cls._REQUESTS_CONFIG['proxies']:
                        del cls._REQUESTS_CONFIG['proxies']

REQUESTS_CONFIG = UserConfig._REQUESTS_CONFIG

