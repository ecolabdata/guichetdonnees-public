"""Requêtes sur l'API CKAN.

Routine Listings
----------------

Initialisation :

    >>> ckan = Ckan()

Création d'une organisation sur l'instance de développement :

    >>> ckan.dev.org_action('create', org_name='driea-75115-01')

Création d'un moissonnage sur l'instance de développement,
puis exécution dudit moissonnage :

    >>> ckan.dev.harvest_action('create', harvest_name='driea-75115-01-h02')
    >>> ckan.dev.run_harvest_job(harvest_name='driea-75115-01-h02')

Exécution d'une requête quelconque sur l'API et lecture de
son résultat :

    >>> my_id = ckan.dev.harvest_id_from_name('driea-75115-01-h02')
    >>> r = ckan.dev.action_request('harvest_source_show_status',
    ...     data_dict={'id': my_id})
    >>> r_print(r)

Mise à jour de toutes les organisations selon le répertoire :

    >>> ckan.dev.refresh_orgs()

Mise à jour de tous les moissonnages selon le répertoire, en forçant
leur exécution "immédiate" :

    >>> ckan.dev.refresh_harvest_sources(re_run=True)

Suppression d'une organisation et de tous les moissonnages, jeux
de données, etc. associés :

    >>> ckan.dev.org_erase(org_name='driea-75115-01')

References
----------
Gestion des organisations et dataset avec l'API CKAN :
https://docs.ckan.org/en/2.9/api/#action-api-reference

Gestion des moissonnages avec l'API CKAN via ckan-harvest :
https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/logic/action

"""
import requests, json, warnings, re
from pathlib import Path
from urllib3.exceptions import InsecureRequestWarning
from time import localtime, strftime, sleep

from maintenance.config import (
    ECOSPHERES_ENV, REQUESTS_CONFIG
)
from maintenance.organization import Organization
from maintenance import __path__

class Ckan:
    """Classe pour l'accès à l'ensemble des instances CKAN.

    Cette classe a autant d'attributs que d'environnements
    définis par :py:data:`ECOSPHERES_ENV`, nommés d'après
    l'identifiant ``name`` de l'environnement.
    
    """
    def __init__(self):
        for env in ECOSPHERES_ENV:
            p = Path(__path__[0]) / 'token/{}.txt'.format(env['name'])
            api_token = None
            if p.exists() and p.is_file():
                with open(p, encoding='utf-8') as src:
                    api_token = src.read()
            setattr(
                self,
                env['name'],
                CkanEnv(
                    env['name'],
                    env['title'],
                    env['url'],
                    api_token=api_token,
                    verify=env.get('verify', True)
                )
            )

class CkanEnv:
    """Classe pour les instances CKAN des différents environnements.

    Parameters
    ----------
    name : str
        Nom court de l'environnement.
    title : str
        Nom littéral de l'environnement.
    url : str
        URL de base de l'instance CKAN.
    api_token : str, optional
        Jeton d'API pour l'instance CKAN.
    verify : bool, default True
        La validité du certificat serveur doit-elle être contrôlée ?

    Attributes
    ----------
    name : str
        Nom court de l'environnement.
    title : str
        Nom littéral de l'environnement.
    url : str
        URL de base de l'instance CKAN.
    api_token : str
        Jeton d'API pour l'instance CKAN.
    verify : bool
        La validité du certificat serveur doit-elle être contrôlée ?
    
    """
    def __init__(self, name, title, url, api_token=None, verify=True):
        self.name = name
        self.title = title
        self.url = url
        self.api_token = api_token
        self.verify = verify

    def get_org_collection(self, force_update=False):
        """Renvoie le répertoire des organisations, en le rechargeant si nécessaire.

        Parameters
        ----------
        force_update : bool, default False
            Force le rechargement du répertoire des organisations
            depuis le fichier ``organizations.json`` du 
            répertoire parent.
        
        Returns
        -------
        dict

        """
        if not force_update and Organization.COLLECTION:
            return Organization.COLLECTION
        Organization.load()
        return Organization.COLLECTION

    def refresh_orgs(self, verbose=True, strict=False):
        """Met à jour toutes les organisations de l'instance selon le répertoire.

        Les nouvelles organisations du répertoire sont créées sur
        l'instance, les organisations qui ont disparu du répertoire
        sont supprimées. Les métadonnées des autres organisations
        sont actualisées selon le répertoire.

        Parameters
        ----------
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        Notes
        -----
        Avant de supprimer une organisation, la fonction supprime
        tous les moissonnages et jeux de données associés. Cette
        dernière opération peut prendre du temps lorsque les jeux
        de données ne sont plus rattachés à un moissonnage, car
        ils sont alors supprimés un par un.
        
        """       
        # ----- liste des organisations de l'instance ------
        r = self.action_request("organization_list")
        # NB : le nombre maximal d'organisations renvoyées
        # par organization_list est 1000 sauf spécifié
        # autrement par le paramètre de configuration
        # ckan.group_and_organization_list_max.
        if not action_success(r):
            raise DialogError(
                "Echec de l'import de la liste"
                " des organisations de l'instance. "
                f"Erreur {r.status_code} : {r.reason}."
            )
        ckan_org = r.json()['result'] or []

        # ------ chargement du répertoire ------
        org_collection = self.get_org_collection()

        # ------ actions ------
        # création ou mise à jour des organisations
        # du répertoire
        for org_name in org_collection:
            a = 'create' if not org_name in ckan_org else 'update'
            r = self.org_action(
                action=a,
                org_name=org_name,
                org_collection=org_collection
                )
            if r is not None:
                m = "{} ({}) : échec de la requête sur l'API CKAN.".format(org_name, a)
                if verbose:
                    print(m)
                if strict:
                    raise DialogError(m)
            elif verbose:
                print("{} : l'organisation a été {}.".format(
                    org_name,
                    'créée' if a == 'create' else 'mise à jour'
                    ))

        # suppression des organisations qui ont disparu du
        # répertoire, en commençant par supprimer les
        # moissonnages associés.
        for org_name in ckan_org:
            if not org_name in org_collection:
                r = self.org_erase(org_name=org_name, verbose=verbose, strict=strict)
                if r is None and verbose:
                    print("{} : l'organisation a été supprimée.".format(org_name))
                # pas de message en cas d'erreur, org_erase s'en charge


    def org_action(self, action, org_name, org_collection=None):
        """Modifie une organisation sur l'environnement considéré.

        Parameters
        ----------
        action : {'create', 'update', 'patch', 'delete', 'purge'}
            L'action à réaliser.
        org_name : str
            L'identifiant (`name`) de l'organisation cible. Elle doit
            être répertoriée dans le répertoire des organisations.
        org_collection : dict, optional
            Le répertoire des organisations. Si non renseigné, la
            fonction le chargera depuis l'export JSON.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.
        
        """    
        if not action in ('create', 'update', 'delete', 'purge', 'patch'):
            raise ValueError("Action inconnue '{}'.".format(action))
        
        if not org_collection and action in ('create', 'update', 'patch'):
            org_collection = self.get_org_collection()

        if action in ('create', 'update', 'patch') and \
            not org_name in org_collection:
            raise ValueError("L'organisation '{}' n'est pas répertoriée." \
                "".format(org_name))

        if action in ('create', 'update', 'patch'):
            data_dict = org_collection[org_name].dict
        else:
            data_dict = {}
        if action in ('update', 'delete', 'purge', 'patch'):
            data_dict.update({ "id": org_name })    

        r = self.action_request("organization_{}".format(action),
            data_dict=data_dict)

        return None if action_success(r) else r

    def refresh_harvest_sources(self, re_run=False, sleep_duration=5,
        verbose=True, strict=False):
        """Met à jour tous les moissonnages de l'instance selon le répertoire.

        Les nouveaux moissonnages du répertoire sont créés sur l'instance,
        les moissonnages qui ont disparu du répertoire sont supprimés.
        Le paramétrage des autres moissonnages est actualisé selon le
        répertoire.
        
        Parameters
        ----------
        re_run : bool, default False 
            Si True, force l'exécution immédiate de tous les moissonnages
            pré-existants. À noter que si `re_run` vaut False, les nouveaux
            moissonnages seront de toute façon exécutés au prochain
            déclenchement du cron.
        sleep_duration : float, default 5
            Durée de la pause entre deux lancements de moissonnages,
            en secondes. Ignoré si `re_run` vaut False. Cf.
            :py:meth:`CkanEnv.run_all_harvest_jobs` pour plus de détails.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        """
        # ----- liste des moissonnages de l'instance ------
        ckan_harvest = self.harvest_sources_list('both')
        ckan_harvest_ids = [v for v in ckan_harvest.values()]

        # ------ chargement du répertoire ------
        harvest_collection = json_import('moissonnages.json')

        # ------ créations et mises à jour ------
        # création ou mise à jour des moissonnages
        # du répertoire
        for harvest_name in ( harvest_collection.keys() if not \
            re_run else reversed(harvest_collection.keys()) ):
            
            harvest_id = ckan_harvest.get(harvest_name)
            a = 'create' if not harvest_name in ckan_harvest else 'patch'
            # on utilise patch et non update pour ne pas perdre
            # les informations générées par CKAN, et considérant que
            # (contrairement aux organisations), les moissonnages
            # ont une structure fixe dans le répertoire (mêmes clés
            # pour tous).
            r = self.harvest_action(
                action=a,
                harvest_name=harvest_name,
                harvest_id=harvest_id,
                harvest_collection=harvest_collection
                )
            if r is not None:
                m = "{} ({}) : échec de la requête sur l'API" \
                    " CKAN.".format(harvest_name, a)
                if verbose:
                    print(m)
                if strict:
                    raise DialogError(m)
            elif verbose:
                print("{} : le moissonnage a été {}.".format(
                    harvest_name,
                    'créé' if a == 'create' else 'mis à jour'
                    ))

            # lancement de la tâche de moissonnage
            # NB : si le cron s'est exécuté entre la création
            # du nouveau moissonnage et l'exécution de cette
            # partie, il pourrait y avoir une erreur ici
            if re_run:
                r = self.run_harvest_job(harvest_name=harvest_name,
                    harvest_id=harvest_id)
                if r is not None:
                    m = "{} : échec du lancement de la tâche de" \
                        " moissonnage.".format(harvest_name)
                    if verbose:
                        print(m)
                    if strict:
                        raise DialogError(m)
                elif sleep_duration:
                    sleep(sleep_duration)

        # ------ suppression ------
        # suppression des moissonnages qui ont disparu du
        # répertoire
        for harvest_name in ckan_harvest.keys():
            if not harvest_name in harvest_collection:

                r = self.erase_harvest(harvest_name=harvest_name,
                    harvest_id=ckan_harvest.get(harvest_name),
                    verbose=verbose, strict=strict)
                if r is None and verbose:
                    print("{} : le moissonnage a été supprimé.".format(harvest_name))
                # pas de message en cas d'erreur, harvest_erase s'en charge


    def harvest_action(self, action, harvest_name=None,
        harvest_id=None, harvest_collection=None, force_manual=False):
        """Modifie un moissonnage sur l'environnement considéré.

        Parameters
        ---------
        action : {'create', 'update', 'patch', 'clear', 'delete'}
            L'action à réaliser.
        harvest_name : str, optional 
            L'identifiant (`name`) du moissonnage cible. Il doit être
            répertorié dans le répertoire des moissonnages.
        harvest_id : str, optional
            L'identifiant technique CKAN (`id`) du moissonnage cible.
        harvest_collection : dict, optional
            Le répertoire des moissonnages. Si non renseigné, la méthode
            le chargera depuis l'export JSON.
        force_manual : bool, default False
            Si True, le moissonnage sera créé ou mis à jour avec une
            fréquence ``MANUAL``, quelle que soit la fréquence spécifiée
            dans le répertoire.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.
        
        Notes
        -----
        Pour l'action ``clear``, `harvest_id` doit obligatoirement être
        spécifié, mais la fonction saura l'obtenir à partir de
        `harvest_name` s'il est renseigné.
        Pour l'action ``delete``, `harvest_id` ou `harvest_name` doit être
        spécifié.
        Pour l'action ``create``, `harvest_name` doit être spécifié.
        Pour les actions ``update`` et ``patch``, `harvest_name` et
        `harvest_id` doivent être spécifiés. La fonction saura obtenir
        `harvest_id` à partir d'`harvest_name` si seul ce dernier est
        renseigné, au prix d'une requête supplémentaire sur l'API.
        
        """
        if not action in ('create', 'update', 'delete', 'clear', 'patch'):
            raise ValueError("Action inconnue '{}'.".format(action))

        if action in ('create', 'update', 'patch') and not harvest_name:
            raise ValueError("L'argument harvest_name est obligatoire" \
                " pour l'action '{}'.".format(action))
        if action in ('clear', 'update', 'patch') and not harvest_id:
            if not harvest_name:
                raise ValueError("L'argument harvest_id est obligatoire" \
                    " pour l'action '{}'. Il pourra être déduit " \
                    "de harvest_name si une valeur est fournie pour" \
                    " ce dernier.".format(action))
            harvest_id = self.harvest_id_from_name(harvest_name)
        if action == 'delete' and not harvest_id and not harvest_name:
            raise ValueError("harvest_id ou harvest_name doit être" \
                "fourni pour l'action '{}'.".format(action))
        
        if not harvest_collection and action in ('create', 'update', 'patch'):
            harvest_collection = json_import('moissonnages.json')

        if action in ('create', 'update', 'patch') and harvest_name \
            and not harvest_name in harvest_collection:
            raise ValueError("Le moissonnage '{}' n'est pas répertorié." \
                "".format(harvest_name))

        if action in ('create', 'update', 'patch'):
            data_dict = harvest_collection[harvest_name].copy()
            if force_manual:
                data_dict.update({ 'frequency': 'MANUAL' })
        else:
            data_dict = {}
        if action in ('update', 'delete', 'clear', 'patch'):
            data_dict.update({ "id": harvest_id or harvest_name })

        r = self.action_request("harvest_source_{}".format(action),
            data_dict=data_dict)

        return None if action_success(r) else r


    def harvest_erase(self, harvest_name=None, harvest_id=None, verbose=True,
        strict=False):
        """Supprime définitivement un moissonnage et les jeux de données associés.

        Parameters
        ----------
        harvest_name : str, optional 
            L'identifiant (`name`) du moissonnage cible. Il doit être
            répertorié dans le répertoire des moissonnages.
        harvest_id : str, optional
            L'identifiant technique CKAN (`id`) du moissonnage cible.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.

        Notes
        -----
        `harvest_name` ou `harvest_id` doit impérativement être renseigné.
        La fonction déduit `harvest_id` de `harvest_name` s'il n'est pas fourni.
        
        La suppression implique plusieurs étapes : suppression des jeux
        de données collectés par le moissonnage, suppression (``delete``) du
        moissonnage, effacement définitif (``purge``) du dataset correspondant
        au moissonnage (pour que son identifiant - `name` - puisse être de
        nouveau utilisé). En cas d'échec sur une étape, les suivantes
        ne sont pas réalisées.
        
        """
        if not harvest_name and not harvest_id:
            raise ValueError("'harvest_id' ou 'harvest_name' doit être spécifié.")
        
        # récupération de l'id du moissonnage, si non spécifié
        harvest_id = harvest_id or self.harvest_id_from_name(harvest_name)
        
        # - suppression des objets dépendants
        r = self.harvest_action('clear', harvest_id=harvest_id)
        if r is not None:
            m = "{} (clear) : échec de la requête sur l'API CKAN.".format(
                harvest_name or harvest_id)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r

        # - suppression du moissonnage
        r = self.harvest_action('delete', harvest_id=harvest_id)
        if r is not None:
            m = "{} (delete) : échec de la requête sur l'API CKAN.".format(
                harvest_name or harvest_id)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r

        # - effacement définitif du moissonnage
        r = self.action_request('dataset_purge', { 'id': harvest_id })
        if not action_success(r):
            m = "{} : échec de la requête sur l'API CKAN.".format(
                harvest_name or harvest_id)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r       


    def org_erase(self, org_name, org_id=None, verbose=True,
        strict=False):
        """Supprime définitivement une organisation, ainsi que les moissonnages et jeux de données associés.

        Parameters
        ----------
        org_name : str
            L'identifiant (`name`) d'une organisation dans le répertoire
            des organisations.
        org_id : str, optional
            L'identifiant technique CKAN (`id`) de l'organisation.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.

        Notes
        -----
        La fonction déduit `org_id` de `org_name` s'il n'est pas fourni.
        
        La suppression implique plusieurs étapes : suppression des
        moissonnages associés, suppression d'éventuels jeux de
        données non liés à des moissonnages, suppression de l'organisation
        (``delete``) et effacement définitif de l'organisation (``purge``).
        En cas d'échec sur une étape, les suivantes ne sont pas réalisées.
        
        """
        # récupération de l'id de l'organisation, si non spécifié
        org_id = org_id or self.org_id_from_name(org_name)

        # liste des moissonnages pour l'organisation
        # (ne fonctionne pas avec name, il faut l'id)
        r = self.action_request('harvest_source_list',
            data_dict={ 'organization_id': org_id })
        if not action_success(r):
            m = "{} (erase) : échec de la récupération de" \
                " la liste des moissonnages de l'organisation".format(
                org_name)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r
        
        ckan_harvest_ids = [e['id'] for e in r.json()['result']] or []

        # suppression des moissonnages (et des jeux associés)
        for harvest_id in ckan_harvest_ids:
            r = self.harvest_erase(harvest_id=harvest_id,
                verbose=verbose, strict=strict)
            if r is not None:
                m = "{} (erase) : échec de la suppression du " \
                    "moissonnage associé '{}'.".format(org_name, harvest_id)
                if verbose:
                    print(m)
                if strict:
                    raise DialogError(m)
                return r
            elif verbose:
                print("{} (erase) : le moissonnage associé '{}' "\
                    "a été supprimé.".format(org_name, harvest_id))

        # suppression d'autres jeux de données résiduels
        n, e, r = self.clear_all_datasets(org_name=org_name,
            org_id=org_id, verbose=verbose, strict=strict)
            # NB: certaines erreurs rencontrées dans cette
            # phase peuvent interrompre l'exécution
        if r is not None:
            m = "{} (erase) : échec de la suppression " \
                  "des jeux de données associés.".format(org_name)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r
        elif verbose and n:
            print("{} (erase) : suppression de {} jeux de données" \
                " orphelins.".format(org_name, n))
    
        # suppression de l'organisation
        r = self.org_action('delete', org_name=org_name)
        if r is not None:
            m = "{} (delete) : échec de la requête sur l'API " \
                "CKAN.".format(org_name)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r
        elif verbose:
            print("{} (delete) : l'organisation a " \
                "été supprimée.".format(org_name))

        # effacement définitif
        r = self.org_action('purge', org_name=org_name)
        if r is not None:
            m = "{} (purge) : échec de la requête sur l'API " \
                "CKAN.".format(org_name)
            if verbose:
                print(m)
            if strict:
                raise DialogError(m)
            return r
        elif verbose:
            print("{} (purge) : l'organisation a été définitivement" \
                " effacée de la base de données.".format(org_name))    


    def action_request(self, api_action, data_dict=None):
        """Lance une requête d'action sur l'API de l'instance CKAN.

        Parameters
        ---------
        api_action : str 
            La commande à activer. Doit être connue de l'API, sinon la
            requête échouera.
        data_dict : dict
            S'il y a lieu, le dictionnaire de paramètres attendu par
            l'API pour la requête considérée.

        Returns
        -------
        requests.Response
            Le résultat renvoyé par requests.
        
        """
        with warnings.catch_warnings():
            if not self.verify:
                warnings.simplefilter("ignore", category=InsecureRequestWarning)
                # pour les avertissements sur la non-vérification
                # des certificats, qui apparaissent sinon à chaque requête
                # envoyée à l'API
            return requests.post(
                "{}/api/3/action/{}".format(self.url, api_action),
                json=data_dict,
                headers={ "Authorization": self.api_token },
                verify=self.verify,
                **REQUESTS_CONFIG
                )
    
    def load_vocabulary(self, vocabularies=None):
        """Lance une requête d'action sur l'API de l'instance CKAN.

        Parameters
        ---------
        vocabularies : str or list(str), optional
            Liste des vocabulaires à charger sur l'instance.
            Si non spécifié, tous les vocabulaires sont considérés.

        Returns
        -------
        requests.Response
            Le résultat renvoyé par requests.
        
        """
        if isinstance(vocabularies, str):
            vocabularies = [vocabularies]
        with warnings.catch_warnings():
            if not self.verify:
                warnings.simplefilter("ignore", category=InsecureRequestWarning)
                # pour les avertissements sur la non-vérification
                # des certificats, qui apparaissent sinon à chaque requête
                # envoyée à l'API
            return requests.post(
                f"{self.url}/api/load-vocab",
                json={'vocab_list': vocabularies} if vocabularies else {},
                headers={ "Authorization": self.api_token },
                verify=self.verify,
                **REQUESTS_CONFIG
                )

    def read_harvest_log(self, limit=10):
        """Affiche les logs de moissonnage dans la console.

        Parameters
        ----------
        limit : int, default 10
            Nombre de lignes de log à afficher.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.
        
        """
        r = self.action_request(
            api_action='harvest_log_list'
        )
        if not action_success(r):
            return r
        j = r.json()['result']
        for k in range(min(limit, len(j))):
            print(json.dumps(j[k]))

    def run_all_harvest_jobs(self, sleep_duration=5,
        verbose=True, strict=False):
        """Relance tous les moissonnages dans l'ordre du répertoire.

        Parameters
        ----------
        sleep_duration : float, default 5
            Durée de la pause entre deux lancements de moissonnages,
            en secondes.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec. Il s'agit de la première réponse reçue
            de l'API qui était porteuse d'une erreur.

        Notes
        -----
        `sleep_duration` permet d'espacer les ordres déclenchement des
        moissonnages, pour accroître les chances qu'ils s'exécutent
        dans le bon ordre. `sleep_duration` doit avoir une durée
        suffisante pour couvrir la phase *gather* du moissonnage,
        afin que l'ordre de lancement des phases *fetch* (sans
        parallélisme) reste identique à celui du lancement des phases
        *gather* (avec parallélisme). Il n'est pas possible de contrôler
        la fin effective de la phase *gather* via l'API
        (``harvest_source_show_status``), car il y a un délai conséquent
        sur la mise à jour de cette information.

        Les moissonages hors répertoire ne sont (silencieusement) pas
        exécutés. Les moissonnages du répertoire qui n'existent pas
        sur l'instance provoquent des messages ou des erreurs selon
        `verbose` et `strict`.

        """
        ckan_harvest = self.harvest_sources_list('both')
        harvest_collection = json_import('moissonnages.json')

        for harvest_name in reversed(harvest_collection.keys()):
            # on prend la liste à l'envers, car ici les tâches
            # seront exécutées dans l'ordre où on les lance,
            # contrairement à ce que fait la fonction équivalente
            # de ckanext-harvest.
            if not harvest_name in ckan_harvest:
                m = "{} : non traité, ce moissonnage n'existe pas sur" \
                    " l'instance CKAN.".format(harvest_name)
                if verbose:
                    print(m)
                if strict:
                    raise ValueError(m)
            else:
                r = self.run_harvest_job(
                    harvest_id=ckan_harvest[harvest_name])
                if r is not None:
                    m = "{} : échec du lancement de la tâche de" \
                        " moissonnage.".format(harvest_name)
                    if verbose:
                        print(m)
                    if strict:
                        raise DialogError(m)
                    return r
                else:
                    print("{} : moissonnage relancé.".format(harvest_name))

                    if sleep_duration:
                        sleep(sleep_duration)


    def run_harvest_job(self, harvest_id=None, harvest_name=None):
        """Relance un moissonnage.

        Parameters
        ---------
        harvest_name : str, optional
            L'identifiant (`name`) d'un moissonnage.
        harvest_id : str
            L'identifiant technique CKAN d'un moissonnage (`id`).

        Returns
        -------
        None
            Si l'action a réussi.
        requests.Response
            En cas d'échec.
        
        Notes
        -----
        `harvest_name` ou `harvest_id` doit impérativement être renseigné. À noter
        que la fonction travaille essentiellement sur `harvest_id`, qui
        est déduit d'`harvest_name` si et seulement s'il n'était pas spécifié.
        Il n'est ainsi jamais vérifié que `harvest_name` et `harvest_id` pointent
        bien sur le même moissonnage si les deux sont fournis, seul
        `harvest_id` est utilisé pour les requêtes.
        
        """
        if not harvest_name and not harvest_id:
            raise ValueError("'harvest_id' ou 'harvest_name' doit être spécifié.")
        
        # il faut l'id du moissonnage, pas son nom
        harvest_id = harvest_id or self.harvest_id_from_name(harvest_name)

        # récupération de la liste des tâches de moissonnage
        r = self.action_request('harvest_job_list', { 'source_id': harvest_id })
        if not action_success(r):
            return r

        l = [ j['id'] for j in r.json()['result']]

        if l:
            # on prend la première tâche de la liste et on la
            # remet dans la queue
            r = self.action_request(
                'harvest_send_job_to_gather_queue', { 'id': l[0] })
            if not action_success(r):
                return r
        else:
            # s'il n'y a pas de tâche déjà définie, on en crée une
            # (et elle sera automatiquement exécutée)
            r = self.action_request('harvest_job_create',
                { 'source_id': harvest_id })
            if not action_success(r):
                return r


    def harvest_id_from_name(self, harvest_name):
        """Récupère l'identifiant technique CKAN d'un moissonnage connaissant son identifiant courant.

        Parameters
        ----------
        harvest_name : str
            L'identifiant (`name`) du moissonnage
            dans le répertoire des moissonnages.

        Returns
        -------
        str
            L'identifiant technique CKAN (`id`) du
            moissonnage.
            
        """
        r = self.action_request('package_show', {'id': harvest_name})
        if not action_success(r):
            raise DialogError("Echec de la récupération de l'identifiant" \
                " CKAN pour le moissonnage '{}'.".format(harvest_name))
        return r.json()['result']['id']


    def org_id_from_name(self, org_name):
        """Récupère l'identifiant technique CKAN d'une organisation connaissant son identifiant courant.

        Parameters
        ----------
        org_name : str
            L'identifiant (`name`) de l'organisation
            dans le répertoire des organisations.

        Returns
        -------
        str
            L'identifiant technique CKAN (`id`) de
            l'organisation.
            
        """
        r = self.action_request('organization_show', {'id': org_name})
        if not action_success(r):
            raise DialogError("Echec de la récupération de l'identifiant" \
                " CKAN pour l'organisation '{}'.".format(org_name))
        return r.json()['result']['id']


    def harvest_sources_list(self, id_or_name='id'):
        """Liste les moissonnages de l'instance.

        Parameters
        ----------
        id_or_name : {'id', 'name', 'both'}, optional
            Si ``'id'``, les identifiants renvoyés sont les identifiants
            techniques de CKAN. Si ``'name'``, ce sont les identifiants
            utilisés pour les URL (et le répertoire des organisations).
            Si ``both``, le résultat sera un dictionnaire avec `name`
            pour clés et `id` pour valeurs.

        Returns
        -------
        list or dict
            Selon `id_or_name`.

        """
        if not id_or_name in ('id', 'name', 'both'):
            raise ValueError("Les seules valeurs autorisées pour id_or_name" \
                " sont 'id', 'name' et 'both'.")
        
        harvest_sources = {} if id_or_name=='both' else []
        rows = 1000 # maximum autorisé sauf paramétrage plus permissif
        start = 0
        while True:
            r = self.action_request(
                'package_search',
                {
                    'fq': '+dataset_type:harvest',
                    'rows': rows,
                    'fl': 'id, name',
                    'start': start
                }
            )
            if not action_success(r):
                raise DialogError(
                    "Impossible de dresser la liste des moissonnages."
                )
            l = r.json()['result']['results']
            if not l:
                break
            if id_or_name=='both':
                harvest_sources.update({ d['name']: d['id'] for d in l })
            else:
                harvest_sources += [ d[id_or_name] for d in l ]
            start += rows
        return harvest_sources


    def org_packages_list(self, org_name=None, org_id=None, id_or_name='id'):
        """Liste les jeux de données d'une organisation.

        Parameters
        ----------
        org_name : str
            L'identifiant (`name`) d'une organisation.
        org_id : str
            L'identifiant technique CKAN de l'organisation (`id`).
        id_or_name : {'id', 'name'}, optional 
            Si ``'id'``, les identifiants renvoyés sont les identifiants
            techniques de CKAN. Si ``'name'``, ce sont les identifiants
            utilisés pour les URL (et le répertoire des organisations).

        Returns
        -------
        list
            Une liste d'identifiants de jeux de données.
        
        Notes
        -----
        `org_name` ou `org_id` doit impérativement être renseigné. À noter
        que la fonction travaille essentiellement sur `org_id`, qui
        est déduit d'`org_name` si et seulement s'il n'était pas spécifié.
        Il n'est ainsi jamais vérifié que `org_name` et `org_id` pointent
        bien sur la même organisation si les deux sont fournis, seul
        `org_id` est utilisé pour les requêtes.
        
        """
        if not id_or_name in ('id', 'name'):
            raise ValueError("Les seules valeurs autorisées pour id_or_name" \
                " sont 'id' et 'name'.")
        if not org_name and not org_id:
            raise ValueError("'org_id' ou 'org_name' doit être spécifié.")
        
        # il faut l'id de l'organisation, pas son nom
        org_id = org_id or self.org_id_from_name(org_name)
        
        packages = []
        rows = 1000 # maximum autorisé sauf paramétrage plus permissif
        start = 0
        while True:
            r = self.action_request(
                'package_search',
                {
                    'fq': '+owner_org:{}'.format(org_id),
                    'rows': rows,
                    'fl': 'id, name',
                    'start': start
                    }
                )
            if not action_success(r):
                raise DialogError("Impossible de dresser la liste des jeux de données" \
                    " de l'organisation '{}'.".format(org_name or org_id))
            l = r.json()['result']['results']
            if not l:
                break
            packages += [ d[id_or_name] for d in l ]
            start += rows
        return packages


    def harvest_packages_list(self, harvest_name=None, harvest_id=None,
        id_or_name='id'):
        """Liste les jeux de données d'un moissonnage.

        Parameters
        ----------
        harvest_name : str
            L'identifiant (`name`) d'un moissonnage.
        harvest_id : str
            L'identifiant technique CKAN d'un moissonnage (`id`).
        id_or_name : {'id', 'name'}, optional 
            Si ``'id'``, les identifiants renvoyés sont les identifiants
            techniques de CKAN. Si ``'name'``, ce sont les identifiants
            utilisés pour les URL.
        
        Returns
        -------
        list
            Une liste d'identifiants de jeux de données (list).
            
        Notes
        -----
        `harvest_name` ou `harvest_id` doit impérativement être renseigné. À noter
        que la fonction travaille essentiellement sur `harvest_id`, qui
        est déduit d'`harvest_name` si et seulement s'il n'était pas spécifié.
        Il n'est ainsi jamais vérifié que `harvest_name` et `harvest_id` pointent
        bien sur le même moissonnage si les deux sont fournis, seul
        `harvest_id` est utilisé pour les requêtes.
        
        """
        if not id_or_name in ('id', 'name'):
            raise ValueError("Les seules valeurs autorisées pour id_or_name" \
                " sont 'id' et 'name'.")
        if not harvest_name and not harvest_id:
            raise ValueError("'harvest_id' ou 'harvest_name' doit être spécifié.")
        
        # il faut l'id du moissonnage, pas son nom
        harvest_id = harvest_id or self.harvest_id_from_name(harvest_name)
        
        packages = []
        rows = 1000 # maximum autorisé sauf paramétrage plus permissif
        start = 0
        while True:
            r = self.action_request(
                'package_search',
                {
                    'fq': '+harvest_source_id:{}'.format(harvest_id),
                    'rows': rows,
                    'fl': 'id, name',
                    'start': start
                    }
                )
            if not action_success(r):
                raise DialogError("Impossible de dresser la liste des jeux de données" \
                    " du moissonnage '{}'.".format(harvest_name or harvest_id))
            l = r.json()['result']['results']
            if not l:
                break
            packages += [ d[id_or_name] for d in l ]
            start += rows
        return packages   


    def clear_all_datasets(self, org_name=None, org_id=None,
        harvest_name=None, harvest_id=None, verbose=True, strict=False):
        """Supprime définitivement tous les jeux de données de l'instance.

        Parameters
        ----------
        org_name : str, optional
            L'identifiant (`name`) d'une organisation dans le répertoire
            des organisations. Si renseigné, seuls les jeux de données
            de l'organisation considérée seront supprimés.
        org_id : str, optional
            L'identifiant technique CKAN (`id`) de l'organisation. Si
            renseigné, seuls les jeux de données de l'organisation
            considérée seront supprimés.
        harvest_name : str, optional
            L'identifiant (`name`) d'un moissonnage dans le répertoire
            des moissonnages. Si renseigné, seuls les jeux de données
            du moissonnage considéré seront supprimés.
        harvest_id : str, optional
            L'identifiant technique CKAN (`id`) d'un moissonnage. Si
            renseigné, seuls les jeux de données du moissonnage considéré
            seront supprimés.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon
            la valeur de `verbose`.

        Returns
        -------
        tuple
            Un tuple avec :
            
            * ``[0]`` le nombre de jeux de données supprimés (int).
            * ``[1]`` le nombre de jeux de données dont la suppression
              a échoué (int).
            * ``[2]`` en cas d'échec d'au moins une requête sur l'API,
              la réponse de requests (requests.Response) pour la première
              requête en erreur. Sinon None.
        
        Notes
        -----
        Si `harvest_id` et `harvest_name` ou `org_id` et `org_name`
        sont tous deux spécifiés, c'est `harvest_id`/`org_id` qui
        servira aux requêtes.
        Si `org_name`/`org_id` et `harvest_name`/`harvest_id` sont
        renseignés en parallèle, la fonction ignore `harvest_id` et
        `harvest_name` et filtrera sur l'organisation uniquement.
        
        """
        n = 0
        e = 0
        r_e = None

        # ------ liste des jeux de données à supprimer ------
        # toute erreur sur les deux premiers cas interrompt l'exécution
        if org_name or org_id:
            l = self.org_packages_list(org_name=org_name, org_id=org_id)
        elif harvest_name or harvest_id:
            l = self.harvest_packages_list(harvest_name=harvest_name,
                harvest_id=harvest_id)
        else:
            r = self.action_request('package_list')
            if not action_success(r):
                r_e = r_e or r
                m = "Impossible de dresser la liste des jeux de données."
                if verbose:
                    print(m)
                if strict:
                    raise DialogError(m)
                return n, e, r_e
            l = r.json()['result']
            # ici l contient les valeurs de name et non id, mais
            # ne devrait pas avoir d'importance

        # ------ suppression ------
        # ici, la gestion des erreurs dépend de strict et verbose
        for j in l:
            # suppression
            r = self.action_request('package_delete', {'id': j})
            if not action_success(r):
                r_e = r_e or r
                m = "{} : échec de la suppression du jeu de " \
                    "données.".format(j)
                if verbose:
                    print(m)
                    e += 1
                    continue
                if strict:
                    raise DialogError(m)
            # effacement définitif
            r = self.action_request('dataset_purge', {'id': j})
            if not action_success(r):
                r_e = r_e or r
                m = "{} : échec de l'effacement définitif du jeu de " \
                    "données.".format(j)
                if verbose:
                    print(m)
                    e += 1
                    continue
                if strict:
                    raise DialogError(m)
            n += 1
            if verbose:
                print('.', end='')

        # ------ résultat ------
        ref = org_name or org_id or harvest_name or harvest_id
        if n and verbose:
            print("\n{} jeux de données supprimés{} ; {} erreurs.".format(
                n,
                " pour {} {}".format(
                    "l'organisation" if org_name or org_id else "le moissonnage",
                    ref
                    ) if ref else "",
                e
                ))
        return n, e, r_e


    def harvest_summary(self, export=False):
        """Construit une table récapitulative des moissonnages.

        Parameters
        ----------
        export : bool, default False
            Le résultat doit-il être sauvegardé dans un fichier ?

        Returns
        -------
        Summary
            Une liste de tuples (un par moissonnage), triés dans l'ordre
            de dernière exécution, avec :
            
            * ``[0]`` l'identifiant technique CKAN du moissonnage (`id`).
            * ``[1]`` l'identifiant sémantique du moissonnage (`name`).
            * ``[2]`` le nombre de jeux de données moissonnés.
            * ``[3]`` le nombre de tâches de moissonnage exécutées.
            * ``[4]`` la date de (fin de la) dernière exécution.
            * ``[5]`` le nombre de jeux ajoutés par le dernier moissonnage.
            * ``[6]`` le nombre de jeux modifiés par le dernier moissonnage.
            * ``[7]`` le nombre de jeux supprimés par le dernier moissonnage.
            * ``[8]`` le nombre d'erreurs lors du dernier moissonnage.
        
        """
        l = Summary()
        l.title = "Bilan des moissonnages ({})".format(self.title)
        l.filename = "moissonnages_{}.md".format(self.name)
        l.header = (
            "Identifiant CKAN - `id`",
            "Identifiant - `name`",
            "Nombre de jeux de données moissonnés",
            "Nombre de tâches de moissonnage exécutées",
            "Dernière tâche : date de fin",
            "Dernière tâche : nombre de jeux ajoutés",
            "Dernière tâche : nombre de jeux modifiés",
            "Dernière tâche : nombre de jeux supprimés",
            "Dernière tâche : nombre d'erreurs"
            )
        d = self.harvest_sources_list('both')
        for harvest_name, harvest_id in d.items():
            r = self.action_request('harvest_source_show_status',
                { 'id': harvest_id })
            if not action_success(r):
                raise DialogError("Impossible de récupérer les" \
                    " informations relatives au moissonnage" \
                    " '{}'.".format(harvest_name))
            e = r.json()['result']
            l.append([
                harvest_id,
                harvest_name,
                e['total_datasets'],
                e['job_count'],
                e['last_job']['finished'],
                e['last_job']['stats']['added'] \
                    if e['last_job']['finished']  else None,
                e['last_job']['stats']['updated'] \
                    if e['last_job']['finished']  else None,
                e['last_job']['stats']['deleted'] \
                    if e['last_job']['finished']  else None,
                e['last_job']['stats']['errored'] \
                    if e['last_job']['finished']  else None
                ])
            print('.', end='')
        
        l.sort(key=lambda x: x[4])

        for n in range(len(l)):
            l[n][4] = re.sub('[.][0-9]*$', '', l[n][4]) if l[n][4] else None
            # on tronque les dates après le tri, car
            # il arrive que deux moissonnages s'achèvent
            # à la même seconde
            l[n] = tuple(l[n])
        
        if export:
            l.export()
        return l
        

class Summary(list):
    """Classe pour les tables de statistiques.

    Une table de statistique est une liste de tuples
    de longueur homogène.

    Attributes
    ----------
    title : str
        Nom de la table.
    filename : str
        Le nom du fichier d'export de la table dans le répertoire
        ``ckan_stats`` (non nécessairement pré-existant).
    header : list
        Les libellés des champs de la table.
    
    """
    def __init___(self):
        self.title = None
        self.filename = None
        self.header = None

    def export(self):
        """Exporte la table de statistiques dans un fichier.

        """
        modified = strftime("%Y-%m-%d %H:%M:%S", localtime())

        txt = "*Dernière modification : {modified}.*\n\n" \
            "# {title}\n\n" \
            "{entete}" \
            "{summary}\n".format(
                modified = modified,
                title = self.title,
                entete = ("| {} |\n| {} ".format(" | ".join(self.header), \
                    " --- |" * len(self.header))) if self else "",
                summary = ("\n| " + " |\n| ".join([" | ".join( \
                    [str(e if e is not None else '-') \
                    for e in t]) for t in self]) + " |") if self else "Aucun."
                )
        
        with open(Path(__path__[0]) / 'ckan_stats/{}'.format(self.filename),
            'w', encoding='utf-8') as dest:
            dest.write(txt)


def action_success(action_result):
    """Détermine le statut d'une requête passée à l'API.

    Parameters
    ----------
    action_result : requests.Response
        Le résultat de la requête, tel que renvoyé par
        requests.

    Returns
    -------
    bool
        True si l'action a réussi, False sinon.
    
    """
    if action_result.status_code == 200 \
        and action_result.json()['success']:
        return True
    else:
        return False


def json_import(filename):
    """Importe un fichier JSON du répertoire parent du module.

    Parameters
    ----------
    filename : str
        Nom du fichier.

    Returns
    -------
    dict or list
        La dé-sérialisation python du JSON.
    
    """
    p = Path(__path__[0]).parent / filename
    if p.exists() and p.is_file():
        with open(p, encoding='utf-8') as src:
            d = json.load(src)
    else:
        raise FileNotFoundError(f"Fichier '{p}' manquant.")
    return d


def r_print(response):
    """Imprime dans la console une réponse de requests.

    Parameters
    ----------
    response : requests.Response
        Résultat d'une requête sur l'API, tel que renvoyé
        par request.

    """
    if response is not None:
        print(json.dumps(response.json(), indent=4, ensure_ascii=False))


class DialogError(Exception):
    """Quand l'API CKAN renvoie une erreur.

    """
