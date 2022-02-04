"""Utilitaires pour l'administration des organisations et moissonnages.

Routine Listings
----------------
Chargement des répertoires mémorisés :

>>> mC = MetaCollection()

Génération du répertoire des organisations avec l'API Annuaire :

>>> mC.org.add_from_apiannuaire()

Sauvegarde du répertoire des organisations :

>>> mC.org.save()

Création des moissonnages :

>>> mC.build_harvest_sources()

Sauvegarde du répertoire des moissonnages :

>>> mC.harvest.save()


References
----------
API "Annuaire des établissements publics de l'administration" :
https://api.gouv.fr/documentation/api_etablissements_publics

Création d'une organisation avec l'API CKAN :
https://docs.ckan.org/en/2.9/api/#ckan.logic.action.create.organization_create

Création d'un moissonnage avec l'API CKAN (extension ckan-harvest) :
https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/logic/action/create.py

"""

import requests, json, re
from pathlib import Path
from organisations.ogcfilter import parse_constraints
from owslib.csw import CatalogueServiceWeb
from time import localtime, strftime

from organisations import __path__

# pour les tests sur le serveur de recette GéoIDE :
# import os
# os.environ['NO_PROXY'] = 'e2.rie.gouv.fr'

ref_org_types = ["ddt", "dreal", "driea", "driea_ut", "driee", "drihl",
    "dir_mer", "did_routes", "dreal_ut", "dtam", "administration-centrale-ou-ministere"]
"""Liste des types d'organisations de l'Annuaire de Service-Public.fr.

"""
    
apiep_url = "https://etablissements-publics.api.gouv.fr"
"""URL de base de l'API "Annuaire des établissements publics de l'administration".

"""

img_dir = "https://raw.githubusercontent.com/ecolabdata/guichetdonnees-public/main/organisations/logos/"
"""URL de base des logos d'organisations.

"""


class MetaCollection:
    """Accès combiné aux répertoires des serveurs CSW, des organisations et des moissonnages.

    Attributes
    ----------
    csw : CswCollection
        Répertoire des serveurs CSW.
    org : OrgCollection
        Répertoire des organisations.
    harvest : HarvestCollection
        Répertoire des moissonnages.
    Statistics : Statistics
        Statistiques sur les moissonnages par organisation et serveur CSW.

    Notes
    -----
    Les classes CswCollection, OrgCollection et HarvestCollection possèdent
    leurs propres méthodes qui permettent de travailler indépendamment sur les
    trois répertoires, mais certaines actions - comme la création des
    moissonnages - nécessitent un accès conjoint aux trois répertoires
    via un objet MetaCollection.
    
    """

    def __init__(self):
        self.csw = CswCollection()
        self.org = OrgCollection()
        self.harvest = HarvestCollection()
        self.statistics = Statistics()
        self.build_statistics(update=False)

    def save(self):
        """Sauvegarde les modifications des répertoires des organisations et des moissonnages, exporte les statistiques.

        """
        self.org.save()
        self.harvest.save()
        self.statistics.export()

    def build_statistics(self, update=True):
        """Génération des statistiques sur les moissonnages.

        Parameters
        ----------
        update : bool, default True
            True si les nombres de fiches doivent être actualisés
            par des requêtes sur le serveur. Les attributs `resources`
            des enregistrements du répertoire des moissonnages sont mis à
            jour en parallèle. Si False, les statistiques sont générées
            à partir des valeurs mémorisées. **True par défaut, et
            peut être très long.**
        
        """
        stat = self.statistics
        stat.modified = strftime("%Y-%m-%d %H:%M:%S", localtime())
        stat.org_records = len(self.org)
        stat.csw_records = len(self.csw)
        stat.harvest_records = len(self.harvest)
        stat.orphan_org = [ o.label_short for o in self.org.values() \
            if not any([ o.name == h['owner_org'] \
            for h in self.harvest.values() ]) ]
        stat.orphan_csw = [ c.title for c in self.csw.values() \
            if not any([ c.url == h['url'] \
            for h in self.harvest.values() ]) ]
        stat.org_no_description = [ o.label_short for o in \
            self.org.values() if not o.get('description') ]
        stat.org_no_logo = [ o.label_short for o in \
            self.org.values() if not o.get('image_url') ]

        if update:
            stat.harvest_resources = 0
            stat.harvest_details = []
            for h in self.harvest.values():
                n = h.ogc_filter.csw_matches(
                    url_csw = h['url'],
                    maxtrials = self.csw[h['url']].maxtrials
                    )
                h.resources = n
                stat.harvested_resources += n
                stat.harvest_details.append((
                    self.org[h['owner_org']].label_short,
                    self.csw[h['url']].title,
                    h.restricted_to,
                    n
                    ))
                
        else:
            stat.harvested_resources = sum([h.resources for h in self.harvest.values()])
            stat.harvest_details = [ ( self.org[h['owner_org']].label_short,
                self.csw[h['url']].title,  h.restricted_to, h.resources ) \
                for h in self.harvest.values() if h['url'] in self.csw \
                and h['owner_org'] in self.org ]        

    def build_harvest_sources(self, org_name=None, url_csw=None,
        org_name_exclude=None, url_csw_exclude=None,
        replace=False, verbose=True, strict=False):
        """Génère des configurations de moissonnage valides pour les CSW x organisations cibles.

        La fonction supprime et crée des enregistrements dans le repertoire
        des moissonnages (attribut :py:attr:`MetaCollection.harvest`). En
        fin d'exécution, elle met à jour les statistiques (attribut
        :py:attr:`MetaCollection.statistics`).

        Parameters
        ----------
        org_name : str or list of str, optional
            Un nom ou une liste d'identifiants d'organisations (attribut
            :py:attr:`OrgRecord.name` et clé du répertoire des organisations).
            Si `org_name` n'est pas renseigné, toutes les organisations du
            répertoire seront traitées. 
        url_csw : str or list of str, optional
            URL ou liste d'URL de serveurs CSW sans aucun paramètre
            (attribut :py:attr:`CswRecord.url` et clé du répertoire des CSW).
            Si `url_csw` n'est pas renseigné, la fonction tentera de créer des
            filtres pour tous les serveurs.
        org_name_exclude : list of str, optional
            Une liste d'identifiants d'organisation (:py:attr:`OrgRecord.name`)
            à ne pas traiter.
        url_csw_exclude : list of str, optional
            Une liste d'URL de serveurs CSW (attribut :py:attr:`CswRecord.url`)
            à ne pas traiter.
        replace : bool, default False
            Si True, les configurations de moissonnage déjà définies pour
            chaque combinaison organisation x serveur CSW considérée seront
            remplacées.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, elles sont ignorées, silencieusement ou non selon la
            valeur de `verbose`. False par défaut.
        
        """
        if isinstance(org_name, str):
            # si org_name n'est pas une liste,
            # on en fait une liste
            org_name = [org_name]

        if isinstance(url_csw, str):
            # si url_csw n'est pas une liste,
            # on en fait une liste
            url_csw = [url_csw]

        for name in org_name or self.org.keys():

            if org_name_exclude and name in org_name_exclude:
                continue

            if len(name) > 96:
                if verbose:
                    print("{} : échec, un identifiant d'organisation " \
                        "ne doit pas dépasser 96 caractères.".format(name))
                if strict:
                    raise ValueError("L'identifiant '{}' dépasse la limite" \
                        " de 96 caractères.".format(name))
                continue

            if not name in self.org:
                if verbose:
                    print("{} : échec, organisation non répertoriée.".format(name))
                if strict:
                    raise ValueError("L'organisation '{}' n'est pas" \
                        " répertoriée.".format(name))
                continue

            org = self.org[name]

            for url in url_csw or self.csw.keys():

                if url_csw_exclude and url in url_csw_exclude:
                    continue

                if not url in self.csw:
                    if verbose:
                        print("{}, {} : échec, serveur CSW non répertorié.".format(name, url))
                    if strict:
                        raise ValueError("Le serveur CSW '{}' n'est pas" \
                            " répertorié.".format(url))
                    continue

                csw = self.csw[url]

                # cas d'exclusions pré-définis
                if ( csw.include is not None and not name in csw.include ) \
                    or ( csw.exclude is not None and name in csw.exclude ) \
                    or ( org.include is not None and not url in org.include ) \
                    or ( org.exclude is not None and url in org.exclude ):
                    # si de tels moissonnages existaient, ils n'ont
                    # pas lieu d'être - on les supprime
                    oldH = [ h for h, v in self.harvest.items() if v['url'] == url \
                        and v['owner_org'] == name ]
                    for h in oldH:
                        del self.harvest[h]
                        if verbose:
                            print("{}, {} : suppression d'un moissonnage non " \
                                "autorisé.".format(name, csw.title))
                    continue

                # moissonnages déjà définis pour l'organisation
                # et le serveur considérés
                oldH = [ h for h, v in self.harvest.items() if v['url'] == url \
                    and v['owner_org'] == name ]
                if oldH and not replace :
                    if verbose:
                        print("{}, {} : non traité, moissonnage " \
                            "pré-existant.".format(name, csw.title))
                    continue
                # si replace, on supprime avant de
                # (probablement) recréer :
                for h in oldH:
                    del self.harvest[h]

                res = None
                
                # cas de moissonnages définis manuellement
                # dans la configuration du CSW            
                if csw.bypass:
                    f = csw.bypass.get(name)
                    if f:
                        res = [(f, f.csw_matches(url) or 0, None)]

                # ... ou dans celle de l'organisation
                if not res and org.bypass_all:
                    
                    if not validate(org.bypass_all, csw.operators):
                        if verbose:
                            print("{}, {} : échec, le filtre 'bypass_all' de l'organisation " \
                                "requiert un opérateur non pris en charge" \
                                " par le serveur.".format(name, csw.title))
                        if strict:
                            raise Exception("Le filtre 'bypass_all' de l'organisation" \
                                " '{}' requiert des opérateurs que le serveur" \
                                " CSW '{}' ne prend pas en charge.".format(name, csw.title))
                        continue
                
                elif not res:
                
                    if not "NOT" in csw.operators and org.base_filter \
                        and any([e[0].upper()=="NOT" for e in org.base_filter]):
                        if verbose:
                            print("{}, {} : échec, le filtre de base de l'organisation " \
                                "requiert l'opérateur NOT, qui n'est pas pris en charge" \
                                " par le serveur.".format(name, csw.title))
                        if strict:
                            raise Exception("Le filtre de base de l'organisation" \
                                " '{}' requiert l'opérateur NOT, que le serveur" \
                                " CSW '{}' ne prend pas en charge.".format(name, csw.title))
                        continue

                if not res:
                    
                    if not "NOT" in csw.operators and csw.base_filter \
                        and any([e[0].upper()=="NOT" for e in csw.base_filter]):
                        if verbose:
                            print("{}, {} : échec, le filtre de base du serveur " \
                                "requiert l'opérateur NOT, alors qu'il n'est pas pris" \
                                " en charge.".format(name, csw.title))
                        if strict:
                            raise Exception("Le filtre de base du serveur" \
                                " '{}' requiert l'opérateur NOT, alors que le serveur" \
                                " ne le prend pas en charge.".format(csw.title))
                        continue
                    
                    res = self.filter_from_org(name, url)
                
                if not res:
                    if verbose:
                        print("{}, {} : échec, aucun filtre standard " \
                            "ne renvoie de résultat.".format(name, csw.title))
                    if strict:
                        raise Exception("Aucun filtre standard ne renvoie" \
                            " de résultat pour l'organisation '{}' et le" \
                            " serveur CSW '{}'.".format(name, csw.title))
                    continue
                for ogc_filter, n, restricted_to in res:

                    # génération d'un identifiant de moissonnage
                    for i in range(98):
                        i += 1
                        hname = "{}-h{}".format(name, str(i).rjust(2, "0"))
                        if not hname in self.harvest:
                            break
                        if i == 99:
                            hname = None

                    if not hname:
                        if verbose:
                            print("{}, {} : échec, impossible de créer un nouvel " \
                                "identifiant de moissonnage.".format(name, csw.title))
                        if strict:
                            raise Exception("Impossible de créer un nouvel " \
                                "identifiant de moissonnage pour " \
                                "l'organisation '{}'.".format(name))
                        continue

                    self.harvest.update({
                        hname: HarvestRecord({
                            'url': url,
                            'name': hname,
                            'owner_org': name,
                            'title': 'CSW {} : {}{}'.format(
                                csw.title,
                                org['title'],
                                " [{}]".format(restricted_to) if restricted_to else ""
                                ),
                            'notes': 'Création {}. {} fiches à date.{}'.format(
                                strftime("%Y-%m-%d %H:%M:%S", localtime()), n,
                                " Moissonnage limité aux {}.".format(restricted_to) \
                                    if restricted_to else ""
                                ),
                            'source_type': 'csw',
                            'frequency': org.frequency or csw.frequency,
                            'config': json.dumps(
                                {
                                    "maxtrials": csw.maxtrials,
                                    "ogcfilter": ogc_filter,
                                    "default_extras": {
                                        "Catalogue source": "{} ({})".format(
                                            csw.title, csw.page) 
                                        }
                                },
                                ensure_ascii=False
                                )
                            },
                            resources=n,
                            ogc_filter=ogc_filter,
                            restricted_to=restricted_to
                            )
                        })
                    
                    if verbose:
                        print("{}, {} : un moissonnage a été " \
                            "défini{}.".format(
                                name, csw.title,
                                " ({})".format(restricted_to) if restricted_to else ""
                                ))

        # mise à jour des statistiques
        self.build_statistics(update=False)
        if verbose:
            print("Les statistiques ont été mise à jour.")


    def write_basic_metadata(self, org_name=None, org_type=None, verbose=True):
        """Génère des descriptifs standard pour les organisations.

        Si ni `org_name` ni `org_type` n'est spécifié, tous les enregistrements
        du répertoire sont traités.
        
        Parameters
        ----------
        org_name : str or list of str, optional
            Un nom ou une liste d'identifiants d'organisations (attribut
            :py:attr:`OrgRecord.name` et clé du répertoire des organisations)
            pour lesquelles ont souhaite générer les métadonnées.
        org_type : str or list of str, optional
            Un type d'établissement ou une liste de types d'établissements.
            Si `org_type` est spécifié, toutes les organisations du type
            considéré seront traitées. `org_type` devrait appartenir à
            :py:data:`ref_org_types` pour avoir une chance d'être reconnu.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.

        See Also
        --------
        OrgRecord.write_basic_metadata
        
        """
        if isinstance(org_name, str):
            org_name = [org_name]

        if org_name:
            for name in org_name:
                if not name in self.org:
                    raise ValueError("L'organisation '{}' n'est pas " \
                        "répertoriée.".format(name))
                res = self.org[name].write_basic_metadata()
                if verbose and res:
                    print("{} : descriptif mis à jour.".format(name))
                elif verbose:
                    print("{} : non traité, pas de descriptif standard " \
                        "pour les organisations de ce type.".format(name))

        if org_type or ( org_type is None and org_name is None ):
            self.org.write_basic_metadata(
                org_type=org_type, verbose=verbose
                )

        self.build_statistics(update=False)
        if verbose:
            print("Les statistiques ont été mise à jour.")


    def get_logo(self, org_name=None, org_type=None, verbose=True):
        """Récupère les URL des logos des organisations.

        Si ni `org_name` ni `org_type` n'est spécifié, tous les
        enregistrements du répertoire sont traités.

        Parameters
        ---------
        org_name : str or list, optional
            L'identifiant (:py:attr:`OrgRecord.name`) de l'organisation
            à traiter ou une liste d'identifiants.
        org_type : str or list of str, optional
            Un type d'établissement ou une liste de types d'établissements.
            Si `org_type` est spécifié, toutes les organisations du type
            considéré seront traitées. `org_type` devrait appartenir à
            :py:data:`ref_org_types` pour avoir une chance d'être reconnu.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.

        See Also
        --------
        OrgRecord.get_logo
        
        """
        if isinstance(org_name, str):
            org_name = [org_name]

        if org_name:
            for name in org_name:
                if not name in self.org:
                    raise ValueError("L'organisation '{}' n'est pas " \
                        "répertoriée.".format(name))
                res = self.org[name].get_logo()
                if verbose and res:
                    print("{} : logo mis à jour.".format(name))
                elif verbose:
                    print("{} : pas de logo disponible.".format(name))

        if org_type or ( org_type is None and org_name is None ):
            self.org.get_logo(
                org_type=org_type, verbose=verbose
                )

        self.build_statistics(update=False)
        if verbose:
            print("Les statistiques ont été mise à jour.")
        

    def filter_from_org(self, org_name, url_csw):
        """Génère un filtre OGC standard à partir du nom d'une organisation.

        Parameters
        ----------
        org_name : str
            L'identifiant d'une organisation du répertoire (valeur de
            l'attribut :py:attr:`OrgRecord.name` et clé du répertoire)
        url_csw : str
            URL du serveur CSW cible, sans aucun paramètre (attribut
            :py:attr:`CswRecord.url` et clé du répertoire des CSW).
            La fonction tient compte des spécificité identifiées
            pour certains serveurs dans la syntaxe des filtres.

        Returns
        --------
        set of tuples
            Chaque tuple est constitué :
            
            * ``[0]`` d'un filtre OGC (OgcFilter) correspondant au paramètre
              `ogcfilter` de la configuration d'un moissonnage.
            * ``[1]`` le nombre de fiches de métadonnées renvoyées par le filtre.
            * ``[2]`` le périmètre du filtre (``'lots'`` ou ``'jeux de données'``),
              dans le cas d'un moissonage différenciés des lots et jeux.
            
            La méthode renvoie None si aucun filtre fonctionnel n'a été trouvé.
        
        """
        csw = self.csw[url_csw]
        org = self.org[org_name]

        res = []

        # opérateurs supportés par le serveur
        operators = csw.operators                            
        
        if not "AND" in operators:
            return
        # la fonction suppose qu'AND au moins est pris
        # en charge, ce qui est toujours vrai pour l'heure.

        # ajustement sur la syntaxe des PropertyIsLike
        # pas de % pour GéoIDE
        f = csw.format_function

        org_base = format_filter(org.base_filter, f)

        for restricted_to, restrict_filter in \
            (csw.restrictions or { "all": [] }).items():

            end = False
            ogc_filter = OgcFilter()

            if restricted_to == 'all':
                restricted_to = None

            # ------- bypass_all -------
            if org.bypass_all:
                # pas d'org_base, et on n'ajoutera pas
                # org.add_filter non plus
                ogc_filter = distribute(
                    format_filter(org.bypass_all, f),
                    csw.base_filter + restrict_filter
                    )
                # on garde le filtre même s'il ne renvoie
                # rien, le test final donnera le compte
                end = True

            # ------- administration centrale ------
            if org.type == "administration-centrale-ou-ministere" and not end:
                # filtre : < décomposition du type d'organisation >
                if org.type_keywords:
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["PropertyIsLike", "OrganisationName", f(k)] \
                            for k in org.type_keywords ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators:
                        if not n:
                            ogc_filter = OgcFilter()
                        else:
                            end = True
                # filtre : < sigle >
                # ... pourrait ne pas être suffisamment discrimant
                # pour de gros catalogues brassant beaucoup de données
                if org.type_short and not end:
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["PropertyIsLike", "OrganisationName", f(org.type_short)] ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators and not n:
                        ogc_filter = OgcFilter()
                end = True

            # ------ service déconcentré -------
            # cas d'une unité départementale
            # filtre : < décomposition du libellé de l'unité >
            if org.unit_keywords and not end:
                ogc_filter.append(
                    org_base + csw.base_filter + restrict_filter + \
                    [ ["PropertyIsLike", "OrganisationName", f(k)] \
                        for k in org.unit_keywords ]
                    )
                n = ogc_filter.csw_matches(url_csw)
                if not "OR" in operators:
                    if not n:
                        ogc_filter = OgcFilter()
                    else:
                        end = True
            
            # filtre : < sigle AND numéro de département >
            if org.type_short and org.area_code and not end:
                supp = self.org.disambiguate_area(
                    'area_code', org_name
                    )
                if not supp is None and (not supp or 'NOT' in operators):
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["Not", "PropertyIsLike", "OrganisationName", f(k)] \
                            for k in supp ] + \
                        [ ["PropertyIsLike", "OrganisationName", f(org.area_code)], \
                            ["PropertyIsLike", "OrganisationName", f(org.type_short)] ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators:
                        if not n:
                            ogc_filter = OgcFilter()
                        else:
                            end = True

            # filtre : < décomposition du type d'organisation
            # AND numéro de département >
            if org.type_keywords and org.area_code and not end:
                supp = self.org.disambiguate_area(
                    'area_code', org_name
                    )
                if not supp is None and (not supp or 'NOT' in operators):
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["Not", "PropertyIsLike", "OrganisationName", f(k)] \
                            for k in supp ] + \
                        [ ["PropertyIsLike", "OrganisationName", f(k)] \
                            for k in org.type_keywords + [f(org.area_code)] ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators:
                        if not n:
                            ogc_filter = OgcFilter()
                        else:
                            end = True

            # les autres filtres ne valent pas pour les divisions
            # territoriales, car basés une décomposition du
            # secteur géographique de l'organisation mère
            if org.unit:
                end = True
            
            # filtre : < sigle AND décomposition du secteur géographique >
            if org.type_short and org.area_keywords and not end:
                supp = self.org.disambiguate_area(
                    'area_keywords', org_name
                    )
                if not supp is None and (not supp or 'NOT' in operators):
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["Not", "PropertyIsLike", "OrganisationName", f(k)] \
                            for k in supp ] + \
                        [ ["PropertyIsLike", "OrganisationName", f(k)] \
                            for k in org.area_keywords + [f(org.type_short)] ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators:
                        if not n:
                            ogc_filter = OgcFilter()
                        else:
                            end = True

            # filtre : < décomposition du type d'organisation AND
            # décomposition du secteur géographique >
            if org.type_keywords and org.area_keywords and not end:
                supp = self.org.disambiguate_area(
                    'area_keywords', org_name, type_only=True
                    )
                if not supp is None and (not supp or 'NOT' in operators):
                    ogc_filter.append(
                        org_base + csw.base_filter + restrict_filter + \
                        [ ["Not", "PropertyIsLike", "OrganisationName", f(k)] \
                            for k in supp ] + \
                        [ ["PropertyIsLike", "OrganisationName", f(k)] \
                        for k in org.area_keywords + org.type_keywords ]
                        )
                    n = ogc_filter.csw_matches(url_csw)
                    if not "OR" in operators:
                        if not n:
                            ogc_filter = OgcFilter()
                        else:
                            end = True

            # ------ filtre additionnel -------
            if org.add_filter and not org.bypass_all and \
               validate(org.add_filter, operators) and \
               (not ogc_filter or "OR" in operators):
                ogc_filter += distribute(
                    format_filter(org.add_filter, f),
                    csw.base_filter + restrict_filter
                    )

            if ogc_filter:
                n = ogc_filter.csw_matches(url_csw)
                if n:
                    res.append((ogc_filter, n, restricted_to))
                
        return res if res else None


    def clean_harvest_sources(self, verbose=True):
        """Supprime du répertoire tous les moissonnages dont le serveur et/ou l'organisation n'est plus répertoriée.

        Parameters
        ----------
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.

        """
        for k, h in self.harvest.copy().items():
            if not 'url' in h or not 'owner_org' in h \
               or not h['url'] in self.csw \
               or not h['owner_org'] in self.org:
                del self.harvest[k]
                if verbose:
                    print("{} : supprimé.".format(k))
                continue
                
        

class Statistics:
    """Classe pour les statistiques sur les moissonnages.

    Attributes
    ----------
    modified : str 
        Date de dernière mise à jour des statistiques,
        au format ``YYYY-mm-dd HH:MM:SS``.
    org_records : int 
        Nombre d'organisations répertoriées.
    csw_records : int 
        Nombre de catalogues répertoriés.
    harvest_records : int 
        Nombre total de moissonnages définis.
    harvested_resources : int 
        Nombre prévisionnel de fiches moissonnées, selon les résultats
        des tests réalisés.
    harvest_details : list of tuple
        Liste de tuples avec :
        
        * ``[0]`` le nom de l'organisation,
        * ``[1]`` le nom du serveur,
        * ``[2]`` si moissonnage d'un sous-ensemble, nom du sous-ensemble,
        * ``[3]`` le nombre de fiches moissonnées.
        
    orphan_org : list of str
        Liste des organisations sans moissonnage associé.
    orphan_csw : list of str
        Liste des catalogues sur lesquels aucun moissonnage n'est défini.
    org_no_description : list of str
        Liste des organisations qui n'ont pas de descriptif.
    org_no_logo : list of str
        Liste des organisations qui n'ont pas de logo.

    Notes
    -----
    La mise à jour des statistiques est réalisée par la méthode
    :py:meth:`MetaCollection.update_statistics`.
    
    """
    def __init__(self):
        self.modified = None
        self.harvest_records = None
        self.harvested_resources = None
        self.harvest_details = []
        self.orphan_org = []
        self.orphan_csw = []
        self.org_no_description = []
        self.org_no_logo = []

    def export(self):
        """Exporte les statistiques au format Markdown.
        
        Le fichier cible est ``statistiques.md``.
        
        """
        if self.modified is None or not self.harvest_details:
            raise ValueError("Les statistiques doivent être générées"\
                " avant d'être exportées.")

        l = sorted(self.harvest_details, key=lambda x: (x[0], x[1]))
        ref = l[0][0]
        table_org = "### {}\n\n".format(ref)
        for e in l:
            if ref != e[0]:
                table_org += "\n### {}\n\n".format(e[0])
                ref = e[0]
            table_org += "- {}{} : {} fiches.\n".format(
                e[1],
                " ({})".format(e[2]) if e[2] else "",
                e[3]
                )

        l = sorted(self.harvest_details, key=lambda x: (x[1], x[0]))
        ref = l[0][1]
        table_csw = "### {}\n\n".format(ref)
        for e in l:
            if ref != e[1]:
                table_csw += "\n### {}\n\n".format(e[1])
                ref = e[1]
            table_csw += "- {}{} : {} fiches.\n".format(
                e[0],
                " ({})".format(e[2]) if e[2] else "",
                e[3]
                )
        
        t = "*Dernière modification : {modified}.*\n\n" \
            "# Statistiques\n\n" \
            "## Général\n\n" \
            "- Nombre d'organisations répertoriées : {org_records}.\n" \
            "- Nombre de catalogues à moissonner : {csw_records}.\n" \
            "- Nombre de moissonnages définis : {harvests_records}.\n" \
            "- Nombre de fiches moissonnées : {harvested_resources}.\n\n" \
            "## Moissonnages par organisation\n\n" \
            "{table_org}\n" \
            "### Organisations orphelines\n\n" \
            "Aucun moissonnage n'est défini pour les organisations suivantes :" \
            "{org_no_harvest}\n\n" \
            "## Moissonnages par catalogue\n\n" \
            "{table_csw}\n" \
            "### Catalogues orphelins\n\n" \
            "Aucun moissonnage n'est défini pour les catalogues suivants :" \
            "{csw_no_harvest}\n\n" \
            "## Métadonnées des organisations\n\n" \
            "### Organisations sans descriptif\n" \
            "{org_no_description}\n\n" \
            "### Organisations sans logo\n" \
            "{org_no_logo}\n\n" \
            "".format(
                modified = self.modified,
                org_records = self.org_records,
                csw_records = self.csw_records,
                harvests_records = self.harvest_records,
                harvested_resources = self.harvested_resources,
                table_org = table_org,
                table_csw = table_csw,
                org_no_harvest = ("\n- " + "\n- ".join(sorted(self.orphan_org))) \
                    if self.orphan_org else " aucune.",
                csw_no_harvest = ("\n- " + "\n- ".join(sorted(self.orphan_csw))) \
                    if self.orphan_csw else " aucun.",
                org_no_description = ("\n- " + "\n- ".join( \
                    sorted(self.org_no_description))) \
                    if self.org_no_description else "\nAucune.",
                org_no_logo = ("\n- " + "\n- ".join(sorted(self.org_no_logo))) \
                    if self.org_no_logo else "\nAucune."
                )

        p = Path(__path__[0]) / 'statistiques.md'
        with open(p, 'w', encoding='utf-8') as dest:
            dest.write(t)


class CswCollection(dict):
    """Classe pour le répertoire des serveurs CSW.

    Le répertoire des serveurs CSW recense les serveurs
    CSW sur lesquels les services déconcentrés publient
    des données. Il contient un enregistrement par serveur.
    Ses clés sont les URL des serveurs (:py:attr:`CswRecord.url`),
    ses valeurs des objets de classe :py:class:`CswRecord` decrivant
    un serveur.
    
    Notes
    -----
    Le répertoire est initialisé avec le contenu du fichier
    ``serveurs_csw.json``.

    """

    def __init__(self):
        p = Path(__path__[0]) / 'serveurs_csw.json'
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                d = json.load(src)
        else:
            raise FileNotFoundError("Fichier 'serveurs_csw.json' " \
                "manquant dans le répertoire courant.")
        if d:
            self.update({ k: CswRecord(v, k) for k, v in d.items() })
      

class OrgCollection(dict):
    """Classe pour le répertoire des organisations.

    Un objet OrgCollection est un dictionnaire avec un
    enregistrement par organisation. Ses clés sont les identifiants
    des organisations (:py:attr:`OrgRecord.name`) et ses valeurs
    des objets de classe :py:class:`OrgRecord` décrivant les organisations.
    
    Notes
    -----
    Le répertoire est initialisé avec le contenu des fichiers
    ``organisations.json`` et ``organisations_config.json``. La méthode
    :py:meth:`OrgCollection.save` permet de sauvegarder en retour les
    modifications réalisées dans ``organisations.json``.
    
    """
    
    def __init__(self):
        p = Path(__path__[0]) / 'organisations.json'
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                d = json.load(src)
        else:
            raise FileNotFoundError("Fichier 'organisations.json' " \
                "manquant dans le répertoire courant.")

        d_config = {}
        p = Path(__path__[0]) / 'organisations_config.json'
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                d_config = json.load(src)
        
        if d:
            self.update({ k: OrgRecord(v, d_config.get(k)) \
                for k, v in d.items() })


    def save(self):
        """Sauvegarde les modifications du répertoire.
        
        """
        self.sort()
        p = Path(__path__[0]) / 'organisations.json'
        if p.exists() and p.is_file():
            with open(p, 'w', encoding='utf-8') as dest:
                json.dump(self, dest, ensure_ascii=False,
                    indent=4)
        else:
            raise FileNotFoundError("Fichier 'organisations.json' " \
                "manquant dans le répertoire courant.")

    def sort(self):
        """Ordonne le répertoire des organisations.

        Veille principalement à ce qu'une organisation mère apparaisse
        toujours avant l'organisation fille.
        
        """
        new_order = []
        for name, org in self.items():
            if 'groups' in org:
                for m in org['groups']:
                    mother = m.get('name')
                    if mother in self and \
                        not mother in new_order:
                        new_order.append(mother)
            if not name in new_order:
                new_order.append(name)
        d = {}
        for k in new_order:
            d.update({k : self[k]})
        self.clear()
        self.update(d)

    def search_name(self, keywords):
        """Renvoie les identifiants des organisations dont le libellé contient les mots listés.

        Parameters
        ----------
        keywords : list of str
            Liste de mots supposés apparaître dans le libellé
            (:py:attr:`OrgRecord.label`) des organisations recherchées
            ou le code de département (:py:attr:`OrgRecord.area_code`).

        Notes
        -----
        La recherche ne tient pas compte de la casse.
        
        """
        l = []
        for name, org in self.items():
            b = True
            for k in keywords:
                if not k.lower() in org.label.lower() \
                    and not k == org.area_code:
                    b = False
                    break
            if b:
                l.append(name)
        if l:
            return l


    def disambiguate_area(self, attribute, org_name, type_only=False):
        """Renvoie les mots-clés à nier pour rendre un filtre identifiant.

        Parameters
        ----------
        attribute : {'area_keywords', 'area_code'}
            Le nom de l'attribut de la classe :py:class:`OrgRecord`
            utilisé pour le filtre.
        org_name : str
            L'identifiant de l'organisation pour laquelle le filtre
            est créé (attribut :py:attr:`OrgRecord.name` et clé du
            répertoire des organisations).
        type_only : bool, default False
            Lorsque la désambiguation ne doit porter que sur les
            organisations de même type. D'une manière générale, il
            est préférable de laisser cette valeur à False,
            sauf quand l'attribut géographique est combiné avec les
            mots clés du type, dont on peut considérer qu'ils suffiront
            à distinguer deux organisations de même aire géographique.

        Returns
        -------
        list of str
            Une liste de mots-clés à ajouter avec ``Not`` +
            ``PropertyIsLike`` à un filtre censé renvoyer les fiches
            de métadonnées de l'organisation `org_name` et constitué
            notamment à partir de l'attribut `attribute`, afin qu'il
            cible bien uniquement l'organisation considérée.
            S'il n'est pas nécessaire d'ajouter de mots-clés, la
            fonction renvoie une liste vide.
            S'il est impossible de rendre le filtre identifiant
            en niant des mots-clés, la fonction renvoie None.

        Notes
        -----
        La désambiguation du filtre ne fonctionne évidemment que
        pour les organisations du répertoire. Il pourrait
        renvoyer des fiches appartenant à d'autres organisations.
        De plus, on ne compare qu'avec les mots clés issus des
        mêmes attributs, c'est loin d'être parfait.
        
        """
        neg = []
        
        myorg_kw = [ self[org_name].area_code ] \
            if attribute == 'area_code' \
            else self[org_name].area_keywords

        for org in self.values():

            if org.name == org_name:
                continue

            if type_only and not org.type == self[org_name].type :
                continue

            if not getattr(org, attribute):
                continue

            org_kw = [ org.area_code ] \
                if attribute == 'area_code' \
                else org.area_keywords

            if set(myorg_kw) == set(org_kw):
                return

            if any([ e in org_kw for e in neg ]):
                # s'il est déjà prévu de nier un des mots-clés,
                # tout va bien.
                # NB : on fait ici le test sur les mots-clés
                # entiers (org_kw = ['DDT', 'Loire'] et
                # neg = ['Loiret'] ne passe pas), pour tenir
                # compte des CSW qui séparent les mots (GéoIDE)
                continue

            if all([ any([ e in k for k in org_kw ]) for e in myorg_kw ]):
                # NB: on ne peut malheureusement pas juste utiliser
                # set(org_kw) < set(myorg_kw) pour tester l'inclusion,
                # car il faut s'assurer que chaque chaîne de caractères
                # de myorg_kw n'est pas incluse dans un mot-clé de org_kw.
                # ex : ['DDT', 'Loire'] est ici inclus dans ['DDT', 'Loiret']
                diff = set(org_kw) - set(myorg_kw)
                while True:
                    p = diff.pop()
                    if not any([ p in e for e in myorg_kw ]):
                        neg.append(p)
                        break
                    if not diff:
                        return

        return neg


    def get_logo(self, org_type=None, verbose=True):
        """Récupère les URL des logos toutes les organisations d'un type.

        Parameters
        ----------
        org_type : str or list of str, optional
            Un type d'établissement ou une liste de types d'établissements.
            `org_type` devrait appartenir à :py:data:`ref_org_types` pour
            avoir une chance d'être reconnu. S'il n'est pas spécifié, toutes
            les organisations du répertoires sont traitées.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.

        See Also
        --------
        OrgRecord.get_logo
        
        """
        if isinstance(org_type, str):
            # si org_type n'est pas une liste,
            # on en fait une liste
            org_type = [org_type]

        for name, org in self.items():
            if not org_type or org.type in org_type:
                res = org.get_logo()
                if verbose and res:
                    print("{} : logo mis à jour.".format(name))
                elif verbose:
                    print("{} : pas de logo disponible.".format(name))


    def write_basic_metadata(self, org_type=None, verbose=True):
        """Génère des descriptifs standard pour toutes les organisations d'un type.

        Parameters
        ----------
        org_type : str or list of str, optional
            Un type d'établissement ou une liste de types d'établissements.
            `org_type` devrait appartenir à :py:data:`ref_org_types` pour
            avoir une chance d'être reconnu. S'il n'est pas spécifié, toutes
            les organisations du répertoires sont traitées.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.

        See Also
        --------
        OrgRecord.write_basic_metadata
        
        """
        if isinstance(org_type, str):
            # si org_type n'est pas une liste,
            # on en fait une liste
            org_type = [org_type]

        for name, org in self.items():
            if not org_type or org.type in org_type:
                res = org.write_basic_metadata()
                if verbose and res:
                    print("{} : descriptif mis à jour.".format(name))
                elif verbose:
                    print("{} : non traité, pas de descriptif standard " \
                        "pour les organisations de type '{}'.".format(
                            name, org.type
                        ))

    
    def add_from_apiannuaire(self, org_type=None, org_name=None,
        replace=False, verbose=True, strict=False):
        """Ajoute une ou plusieurs organisations au répertoire.

        Parameters
        ---------
        org_type : str or list of str
            Un type d'établissement ou une liste de types d'établissements,
            parmi :py:data:`ref_org_types`. Si `org_type` est renseigné,
            toutes les organisations du type considéré seront ajoutées ou mises
            à jour.
        org_name : str or list of str
            Un nom ou une liste d'identifiants d'organisations (attribut
            :py:attr:`OrgRecord.name` et clé du répertoire des organisations).
            Si `org_name` est renseigné, seule la ou les organisations
            listées seront ajoutées / mises à jour.
        replace : bool, default False
            Si True, une organisation pré-existante sera remplacée. Si False,
            elle est ignorée.
        verbose : bool, default True
            Si True, les actions réalisées sont imprimées au fur et à
            mesure dans la console.
        strict : bool, default False
            Si True, les anomalies rencontrées provoquent des erreurs.
            Si False, les organisations concernées sont simplement exclues
            du traitement.

        Notes
        -----
        Si `org_type` et `org_name` sont renseignés simultanément, `org_name`
        prévaut. Si aucun n'est spécifié, toutes les organisations dont le type
        est listé dans :py:data:`ref_org_types` seront ajoutées / mises à jour.

        """
        # ------ Initialisation ------

        if isinstance(org_name, str):
            # si org_name n'est pas une liste,
            # on en fait une liste
            org_name = [org_name]

        # identification des types d'organisation
        # (car l'API ne permet pas de requêter sur les
        # identifiants)
        if org_name:
            org_type = []
            # écrase org_type, s'il était renseigné
            for name in org_name:
                t = org_type_from_name(name)
                if t and not t in org_type:
                    org_typ.append(t)
                else:
                    if verbose:
                        print("{} : non traité, type d'organisation non pris" \
                            " en charge par l'API.".format(name))
                    if strict:
                        raise ValueError("Type d'organisation non pris en " \
                            "charge par l'API pour id='{}'.".format(name))
                
            if not org_type:
                return

        # en l'absence de filtre, on prend tous les
        # types connus (en principe) par l'API
        if not org_name and not org_type:
            org_type = ref_org_types

        # ------ Interrogation de l'API ------
        for otype in org_type:
            org_list = apiannuaire_get(otype)
            
            if not org_list:
                err = "Pas de retour de l'API pour le type '{}'.".format(otype)
                if verbose:
                    print(err)
                if strict:
                    raise FileNotFoundError(err)
                continue
        
            # ------ Traitement ------
            for org in org_list:
            
                if not "properties" in org:
                    err = "Retour de l'API inexploitable pour une organisation " \
                        "de type '{}' (clé 'properties' manquante).".format(otype)
                    if verbose:
                        print(err)
                    if strict:
                        raise KeyError(err)
                    continue

                descr = org['properties']
                
                name = descr.get("id").lower()
                # on passe les identifiants en minuscules, car c'est
                # une contrainte de CKAN
                
                if not name:
                    err = "Retour de l'API inexploitable pour une organisation " \
                        "de type '{}' (clé 'id' manquante).".format(otype)
                    if verbose:
                        print(err)
                    if strict:
                        raise KeyError(err)
                    continue
                
                if org_name and not name in org_name:
                    continue
                
                alreadyExists = name in self
                if (not replace and alreadyExists):
                    if verbose:
                        print("{} : non traité, l'organisation existe déjà".format(name))
                    continue
                
                if not re.fullmatch("[a-z0-9_-]{2,96}", name):
                    # NB : CKAN autorise jusqu'à 100 caractères, mais il
                    # faudra en ajouter 4 pour les identifiants des
                    # moissonnages.
                    if verbose:
                        print("{} : non traité, identifiant invalide.".format(name))
                    if strict:
                        raise ValueError("Identifiant id='{}' invalide.".format(name))
                    continue

                # exclusion silencieuse des UT DREAL
                # (on ne requête sur dreal_ut que parce qu'il
                # ramène normalement aussi les DEAL)
                if otype == 'dreal_ut':
                    dep = re.search(r"[-](\d{2})", name)
                    if dep and not re.fullmatch('9[78]', dep[1]):
                        continue
                
                if not "nom" in descr:
                    if verbose:
                        print("{} : non traité, libellé manquant " \
                            "(clé 'nom').".format(name))
                    if strict:
                        raise KeyError("Organisation sans libellé (clé 'nom'"
                            " pour id='{}').".format(name))
                    continue
                
                self.update({
                    name: OrgRecord({
                        "name": name,
                        "label": clean_label(descr['nom'], " - ")
                        })
                    })
                
                self[name].update({ 'title': self[name].title })

                # métadonnées additionnelles si disponibles
                extras = []
                for e, alias in { "email": "Courriel", "telephone": "Téléphone",
                    "url": "Site internet" }.items():
                    if e in descr:
                        extras.append({ "key": alias, "value": descr[e] })
                if extras:
                    self[name].update({ "extras": extras })

                # ajout des descriptifs basiques déduits du
                # type d'organisation
                self[name].write_basic_metadata()

                # logo
                self[name].get_logo()

                if verbose and alreadyExists:
                    print("{} : mis à jour.".format(name))
                elif verbose:
                    print("{} : créé.".format(name))


class HarvestCollection(dict):
    """Classe pour le répertoire des moissonnages.

    Chaque enregistrement du répertoire correspond à un moissonnage
    à définir dans CKAN. La clé est un identifiant (identifiant de
    l'organisation dont les métadonnées sont moissonnées + numéro d'ordre),
    la valeur est le dictionnaire de paramètres à passer en argument lors de
    la requête ``harvest_source_create`` sur l'API de CKAN - cf.
    https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/
    logic/action/create.py.
    
    Notes
    -----
    Le répertoire est initialisé avec le contenu du fichier
    ``moissonnages.json`` et la méthode :py:meth:`HarvestCollection.save`
    permet d'y sauvegarder en retour les modifications réalisées.
    
    """

    def __init__(self):
        p = Path(__path__[0]) / 'moissonnages.json'
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                d = json.load(src)
        else:
            raise FileNotFoundError("Fichier 'moissonnages.json' " \
                "manquant dans le répertoire courant.")
        if d:
            self.update({ k: HarvestRecord(v) for k, v in d.items() })

    def save(self):
        """Sauvegarde les modifications du répertoire.
        
        """
        self.sort()
        p = Path(__path__[0]) / 'moissonnages.json'
        if p.exists() and p.is_file():
            with open(p, 'w', encoding='utf-8') as dest:
                json.dump(self, dest, ensure_ascii=False,
                    indent=4)
        else:
            raise FileNotFoundError("Fichier 'moissonnages.json' " \
                "manquant dans le répertoire courant.")

    def sort(self):
        """Ordonne le répertoire des moissonnages.

        L'ordre de priorité des serveurs CSW est spécifié dans
        ``serveurs_csw_ordre.json`` (ordre de la liste, ceux qui n'y
        apparaissent pas seront traités à la fin dans un ordre
        arbitraire).

        Notes
        -----
        L'ordre du répertoire est inversé par rapport à l'ordre attendu
        des moissonnages, car les "queues" de CKAN se comportent visiblement
        comme des piles (*first in, last out*).
        
        """
        p = Path('serveurs_csw_ordre.json')
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                l = json.load(src)
                l.reverse()
        else:
            l = []

        old_order = list(self)
        new_order = sorted(
            old_order,
            key=lambda x: (
                l.index(self[x]['url']) if self[x]['url'] in l \
                    else 0,
                old_order.index(x)
                )
            )
        # on trie sur l'ordre de moissonnage des CSW
        # défini par serveurs_csw_ordre.json ET sur
        # l'ordre antérieur, car il faut
        # conserver l'ordre des moissonnages
        # différenciés selon "restrictions".
        d = {}
        for k in new_order:
            d.update({k : self[k]})
        self.clear()
        self.update(d)            


class CswRecord:
    """Classe pour un enregistrement du répertoire des organisations.

    Un objet de classe `CswRecord` représente un serveur CSW.
    
    Parameters
    ----------
    csw : dict
        Dictionnaire décrivant le serveur. Il devrait au moins avoir une
        clé `title`, une clé `kind` et une clé `page`. Tous les attributs
        de la classe peuvent être définis à l'initialisation par la valeur
        d'une clé de même nom dans `csw`, à l'exception de `format_function`.
    url : str
        L'URL du serveur (attribut :py:attr:`CswRecord.url` et clé du répertoire
        des serveurs CSW).

    Attributes
    ----------
    url : str
        L'URL du serveur CSW, sans aucun paramètre.
    title : str
        Le libellé du catalogue mettant à disposition le service CSW.
    page : str
        URL de la page d'accueil grand public du catalogue.
    kind : str
        Le type de serveur. Actuellement ``'geoide'`` ou ``'geonetwork'``,
        mais d'autres valeurs pourraient être ajoutées à l'avenir.
    base_filter : list
        Une liste de conditions à combiner (``AND``) systématiquement à tout
        filtre défini pour le serveur. À noter que si les conditions font
        appel à l'opérateur ``NOT`` et que celui-ci n'est pas pris en charge
        par le serveur, aucun moissonnage ne sera défini.
        Exemple avec un élément :
        ``[["PropertyIsEqualTo", "dc:type", "dataset"]]``.
        Exemple avec deux éléments :
        ``[["PropertyIsEqualTo", "dc:type", "dataset"], ["Not", "PropertyIsLike", "OrganisationName", "SANDRE"]]``.
    frequency : {'WEEKLY', 'MANUAL', 'MONTHLY', 'BIWEEKLY', 'DAILY', 'ALWAYS'}
        La fréquence de moissonnage par défaut pour le serveur, (réf :
        https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py).
        Si non renseignée lors de l'initialisation, ``'WEEKLY'`` est
        utilisé.
    maxtrial : int
        Nombre maximal de tentatives d'interrogation du serveur avant que
        la fonction ne se résolve à renvoyer une erreur. Si non renseigné,
        l'initialisation fixe la valeur à 5.
    restrictions : dict
        Dans le cas d'un serveur où le moissonnage des lots doit être séparé
        de celui des jeux de données, un dictionnaire dont les clés sont ``'lots'``
        et ``'jeux de données'`` et les valeurs les filtres à utiliser. L'ordre des
        clés est l'inverse de l'ordre dans lequel les moissonnages devront être
        effectués. Il est possible de définir d'autres sous-domaines de moissonnages
        que les lots et les jeux.
    operators : list of str
        La liste des opérateurs pris en charge. Par défaut, il sera considéré
        à l'initialisation que cette liste est ``['AND', 'OR', 'NOT']``, mais
        une liste plus restreinte peut être spécifiée. A minima, ``AND`` doit
        être pris en charge.
    include : list of str
        S'il y a lieu, liste blanche des identifiants d'organisations
        (:py:attr:`OrgRecord.name`) pour lesquelles des moissonnages peuvent
        être créés sur le catalogue. Si cet attribut n'est pas défini
        :py:meth:`MetaCollection.build_harvest_sources` considère que toutes
        les organisations sont autorisées.
    exclude : list
        S'il y a lieu, liste noire d'identifiants d'organisations
        (:py:attr:`OrgRecord.name`) qui ne doivent pas avoir de moissonnages
        sur le catalogue.
    bypass : dict
        S'il y a lieu, un dictionnaire dont les clés sont des identifiants
        d'organisations (:py:attr:`OrgRecord.name`) et les valeurs les filtres
        OGC (:py:class:`OgcFilter`) à utiliser pour lesdites organisations.
        Lors de la création des moissonnages, si un filtre est recensé dans
        `bypass` pour le couple CSW x organisation, c'est lui qui est utilisé
        au lieu d'un filtre calculé. Les filtres de `bypass` sont présumés déjà
        inclure les conditions de `base_filter`, s'il y avait lieu.
    format_function : function
        Fonction à appliquer aux chaînes de caractères arguments des
        ``PropertyIsLike``. Concrètement, met ou non des ``%`` autour des termes
        selon le serveur.
        
    """
    
    def __init__(self, csw, url):
        for e in ('title', 'page', 'kind'):
            if not e in csw:
                raise CswImportError("Clé '{}' manquante" \
                    " ('{}').".format(e, url))
        
        self.url = url
        self.title = csw['title']
        self.page = csw['page']
        self.kind = csw['kind']
        self.base_filter = csw.get('base_filter') or []
        self.frequency = csw.get('frequency') or 'WEEKLY'
        self.maxtrials = csw.get('maxtrials') or 5
        self.restrictions = csw.get('restrictions')
        self.include = csw.get('include')
        self.exclude = csw.get('exclude')
        self.operators = csw.get('operators') or \
            ["AND", "OR", "NOT"]

        if not "AND" in self.operators:
            raise CswImportError("La prise en charge de l'opérateur" \
                " 'AND' est requise ({}).".format(url))

        self.bypass = { k: OgcFilter(f) for k, f in csw['bypass'].items() } \
            if 'bypass' in csw else {}
        self.format_function = ( lambda x: x ) if self.kind == 'geoide' \
            else ( lambda x: '%{}%'.format(x) )


class OrgRecord(dict):
    """Classe pour un enregistrement du répertoire des organisations.

    Un enregistrement du répertoire des organisations correspond
    au dictionnaire de paramètres à fournir à l'API CKAN pour
    créer ladite organisation.
    
    Clés obligatoires :
    
    * `name` : str
      Nom de l'organisation, ou en fait plutôt un identifiant litéral.
      2 à 100 caractères alpha-numériques minuscules + ``_`` et ``-``.
      En principe identique à l'attribut :py:attr:`OrgRecord.name`,
      sauf modification manuelle post-initialisation.
    * `title` : str
      Libellé court de l'organisation, qui est celui qu'utilise
      CKAN pour nommer les organisations dans le front office.
      Si non présente, elle est recalculée automatiquement.
      En principe identique à l'attribut :py:attr:`OrgRecord.title`,
      sauf modification manuelle post-initialisation.
    * `label` : str
      Libellé long de l'organisation. En principe identique à
      l'attribut :py:attr:`OrgRecord.label`, sauf modification
      manuelle post-initialisation.

    Clés optionnelles :
    
    * `description` : str
      Description de l'organisation.
    * `image_url` :  str
      URL du logo de l'organisation.
    * `extras` : dict
      Dictionnaire contenant des métadonnées complémentaires.

    L'API CKAN prévoit d'autres clés, mais elles ne sont pas utilisées.
    Cf. https://docs.ckan.org/en/2.9/api/#ckan.logic.action.create.organization_create.

    Parameters
    ----------
    org : dict
        Le dictionnaire décrivant l'organisation. Il doit au moins avoir
        une clé `name` et une clé `title`. S'il y a lieu, il peut contenir
        les clés optionnelles listées ci-avant et des clés nommées d'après
        les attributs de configuration des moissonnages listés ci-après
        (`base_filter` et suivants), qui définiront les valeurs de ces
        attributs. Les autres attributs sont calculés quoi qu'il arrive.
    org_config : dict, optional
        Dictionnaire contenant les informations de configuration
        additionnelle, le cas échéant.

    Attributes
    ----------
    name : str
        L'identifiant de l'organisation, de la forme
        [type d'organisation]-[code INSEE de la commune]-[numéro
        d'ordre sur deux caractères]. Ces identifiants sont ceux de
        l'annuaire de Service-Public.fr. En principe identique à la
        clé `name` du dictionnaire.
    title : str
        Libellé court de l'organisation. En principe identique à la clé
        `title` du dictionnaire.
    label : str
        Libellé long de l'organisation. En principe identique à la clé
        `label` du dictionnaire.
    label_short : str
        Variante raccourcie de `label`, qui sert essentiellement pour
        les statistiques.
    area : str
        Le libellé du secteur géographique de l'organisation.
    area_code : str
        Le numéro de département de l'organisation, le cas échéant.
    area_keywords : list
        Liste des mots clés représentant le secteur géographique de
        l'organisation.
    type : str
        Type d'établissement, parmi :py:data:`ref_org_types`. À noter
        que les DEAL sont classées sous ``'dreal_ut'``. Ces types sont
        une catégorisation artificielle de l'annuaire de Service-Public.fr,
        ils n'ont pas de sens en tant que tel, au contraire des valeurs
        de `type_short` et `type_long`.
    type_short : str
        Le sigle correspondant au type d'organisation (DDT, DDTM, DREAL...).
    type_long : str
        Le libellé long du type d'organisation.
    type_keywords : list or str
        Liste des mots clés représentant le type d'organisation.
    `unit` : str
        Pour une organisation qui est une division territoriale d'une autre,
        le libellé de la division.
    unit_keywords : list of str
        Liste de mots clés représentant la division territoriale.
    base_filter : list of list of str
        Une liste de conditions à combiner (``AND``) systématiquement à tout
        filtre défini pour l'organisation. À noter que si les conditions font
        appel à l'opérateur ``NOT`` et que celui-ci n'est pas pris en charge
        par le serveur, aucun moissonnage ne sera défini. Les ``PropertyIsLike``
        doivent être écrits sans ``%``, ils seront ajoutés ou non selon ce qui
        est préférable pour le serveur considéré.
    add_filter : OgcFilter
        Un filtre OGC à ajouter (``OR``) aux filtres définis automatiquement
        pour les moissonnages de l'organisation, sous réserve que l'opérateur
        ``OR`` soit bien pris en charge par le serveur et que tous les opérateurs
        utilisés par le filtre soient pris en charge. Si aucun filtre automatique
        ne renvoie de résultat, c'est le filtre additionnel qui sera utilisé.
        Les filtres additionnels sont combinés avec le :py:attr:`CswRecord.base_filter`
        du CSW, mais sont présumés déjà inclure le `base_filter` de l'organisation
        s'il y avait lieu.
    frequency : str
        La fréquence de moissonnage pour l'organisation. Le cas échéant, elle prévaut
        sur la fréquence définie pour le serveur.
    include : list of str
        S'il y a lieu, liste fermée des serveurs CSW (:py:attr:`CswRecord.url`) pour
        lesquels des moissonnages peuvent être créés. Si cet attribut n'est pas défini,
        :py:meth:`MetaCollection.build_harvest_sources` considère que tous les serveurs
        sont autorisés.
    exclude : list of str
        S'il y a lieu, liste d'identifiants de serveurs CSW (:py:attr:`CswRecord.url`)
        pour lesquels aucun moissonnage ne doit être défini.
    bypass_all : OgcFilter
        S'il y a lieu, le filtre OGC à utiliser pour tous les moissonnages de
        l'organisation. À noter que les filtres des attributs :py:attr:`CswRecord.bypass`
        des serveurs prévalent sur `bypass_all`.
        `bypass_all` est présumé inclure les conditions du `base_filter` de
        l'organisation s'il y avait lieu. Il sera combiné avec le
        :py:attr:`CswRecord.base_filter` du CSW et les filtres de
        :py:attr:`CswRecord.restrictions` s'il y a lieu. Si `bypass_all` fait appel
        à des opérateurs non pris en charge par un serveur CSW, aucun moissonnage
        ne sera défini pour ce serveur.
    
    """

    def __init__(self, org, org_config=None):
        self.name = None
        self.title = None
        self.label = None
        self.label_short = None
        self.area = None
        self.area_code = None
        self.area_keywords = []
        self.type = None
        self.type_short = None
        self.type_long = None
        self.type_keywords = []
        self.unit = None
        self.unit_keywords = []

        for e in ('label', 'name'):
            if not e in org:
                raise OrgImportError("Clé '{}' manquante" \
                    ".".format(e))
        
        self.update({ k: v for k, v in org.items() })

        self.name = org['name']
        self.title = org.get('title')
        self.label = org['label']

        self.type = org_type_from_name(self.name)
        sttl = split_label(self.label, self.type)

        self.type_long = sttl[0]

        typ = re.search(r"^(.*?)\s*(:?[(].*)?$", sttl[0])
        if typ:
            self.type_keywords = extract_keywords(typ[1])

        sigle = re.search("[(]([^)]+)[)]", sttl[0])
        if sigle:
            self.type_short = sigle[1]

        if self.type != "administration-centrale-ou-ministere":
            self.area = sttl[1]
            self.area_keywords = extract_keywords(sttl[1])

        # services départementaux
        if self.type in ('ddt', 'dtam', 'dreal_ut', 'driea_ut'):
            dep = re.search(r"[-](\d[0-9ab])", self.name)
            if dep and re.fullmatch('9[78]', dep[1]):
                dep = re.search(r"[-](\d{3})", self.name)
            if dep:
                self.area_code = dep[1].upper()
        
        # division terrioriale (type 'driea_ut')
        if len(sttl) == 3:
            self.unit = sttl[2]
            self.unit_keywords = extract_keywords(sttl[2])                
            if self.type_short:
                self.label_short = "{} - {}{}".format(
                    self.type_short,
                    self.unit,
                    " ({})".format(self.area_code) \
                        if self.area_code else ""
                    )
                if not self.title:
                    self.title = "{}{} - {}".format(
                        self.type_short,
                        " {}".format(self.area) if self.area \
                            else "",
                        "UD {}".format(self.area_code) \
                            if self.area_code else self.unit
                        )
                    self.update({ 'title': self.title })
            else:
                self.label_short = self.label
                if not self.title:
                    self.title = self.label
                    self.update({ 'title': self.title })
        elif self.type_short:
            self.label_short = "{} {}{}".format(
                self.type_short,
                self.area,
                " ({})".format(self.area_code) \
                    if self.area_code else ""
                ) if self.area else self.type_short
            if not self.title:
                self.title = "{}{}".format(
                    self.type_short,
                    " {}".format(self.area_code) if self.area_code \
                        else " {}".format(self.area) if self.area else ""
                    )
                self.update({ 'title': self.title })
        else:
            self.label_short = self.label
            if not self.title:
                self.title = self.label
                self.update({ 'title': self.title })

        # attributs de configuration des moissonnages
        if org_config:
            self.base_filter = org_config.get('base_filter') or []
            self.bypass_all = OgcFilter(org_config.get('bypass_all'))
            self.add_filter = OgcFilter(org_config.get('add_filter'))
            self.include = org_config.get('include')
            self.exclude = org_config.get('exclude')
            self.frequency = org_config.get('frequency')
        else:
            self.base_filter = []
            self.bypass_all = None
            self.add_filter = None
            self.include = None
            self.exclude = None
            self.frequency = None


    def get_logo(self):
        """Génére l'URL du logo de l'organisation.

        La clé `image_url` du dictionnaire est mise à jour
        avec l'URL trouvée, ou supprimée si aucun logo
        n'est plus disponible.

        Returns
        -------
        bool
            True si un logo a été trouvé.
            False sinon.

        Notes
        -----
        L'image doit :
        
        * avoir été poussée sur le Git, et donc se trouver
          effectivement dans ``img_dir`` ;
        * être nommée d'après l'identifiant de l'organisation
          (:py:attr:`OrgRecord.name`) ou son type
          (:py:attr:`OrgRecord.type`). La fonction cherche
          d'abord une correspondance sur l'identifiant, donc
          il est possible d'avoir un logo "type" qui fera office de
          valeur par défaut pour les organisation du type
          qui n'ont pas de logo spécifique.

        Si plusieurs formats sont disponibles, la fonction
        en retiendra un arbitrairement.

        """
        image_url = None
        
        # recherche d'une correspondance sur name :
        for e in ('.jpeg', '.jpg', '.png', '.svg'):
            if exists_url(img_dir + self.name + e):
                image_url = img_dir + self.name + e
                break
        
        # recherche d'une correspondance sur type :
        if not image_url:
            for e in ('.jpeg', '.jpg', '.png', '.svg'):
                if exists_url(img_dir + self.type + e):
                    image_url = img_dir + self.type + e
                    break
        
        if image_url:
            self.update({ "image_url": image_url })
        elif "image_url" in self:
            del self["image_url"]
        
        return True if image_url else False

   
    def write_basic_metadata(self):
        """Génère des métadonnées basiques sur l'organisation.

        Si un descriptif basique a été défini pour le type
        d'organisation considéré, la fonction met à jour la clé
        `description` avec un descriptif sommaire de
        l'organisation.

        Returns
        -------
        bool
            True si le dictionnaire a effectivement été modifié,
            False sinon (ce qui arrivera pour un type d'établissement
            qui n'apparaît pas dans ``descriptifs_basiques.json``).       

        Notes
        -----
        La fonction utilise largement les attributs de l'objet
        :py:class:`OrgRecord`, qui doivent donc avoir été
        correctement générés au préalable (comme c'est normalement
        le cas à l'initialisation).
        
        """
        p = Path('utils/descriptifs_basiques.json')
        if p.exists() and p.is_file():
            with open(p, encoding='utf-8') as src:
                d = json.load(src)
        else:
            raise FileNotFoundError(
                "Fichier 'descriptifs_basiques.json' " \
                "manquant dans le répertoire courant."
                )
        if not self.type or not self.type in d:
            return False

        description = d[self.type].get("description", "").format(
            label=re.sub('\s[(][^)]*[)]', '', self.label),
            title=self.title,
            area=self.area,
            littoral=(d[self.type].get("littoral", '') \
                if self.type_short == 'DDTM' else '')
            ) or None

        if description:
            self.update({ 'description': description })
        elif "description" in self:
            del self["description"]

        return True


class HarvestRecord(dict):
    """Classe pour un enregistrement du répertoire des moissonnages.

    Parameters
    ---------
    harvest : dict
        Le dictionnaire contenant la configuration du moissonnage.
    resources : int, optional
        Nombre de fiches moissonnées à date.
    restricted_to : str, optional
        Périmètre de restriction de l'objet du moissonnage. Peut
        notamment valoir ``'lots'`` ou ``'jeux de données'`` lorsque
        les deux sont moissonnés séparément.
    ogc_filter : OgcFilter, optional
        Le filtre utilisé par le moissonnage.

    Attributes
    ----------
    resources : int
        Nombre de fiches moissonnées à date.
    restricted_to : str
        Périmètre de restriction de l'objet du moissonnage. Peut
        notamment valoir ``'lots'`` ou ``'jeux de données'`` lorsque
        les deux sont moissonnés séparément.
    ogc_filter : OgcFilter
        Le filtre utilisé par le moissonnage.

    Notes
    -----
    Si leurs valeurs ne sont pas fournies en argument à l'initialisation,
    `__init__` tente d'initialiser les attributs à partir de la
    configuration mémorisée dans `harvest`, notamment le champ `notes`,
    dont il importe de préserver la syntaxe (il est possible d'ajouter
    des informations à la suite).
    
    """

    def __init__(self, harvest, resources=None,
        restricted_to=None, ogc_filter=None):
        self.resources = resources
        self.restricted_to = restricted_to
        self.ogc_filter = ogc_filter or OgcFilter([])
        self.update({ k: v for k, v in harvest.items() })

        if 'notes' in harvest and resources is None:
            r = re.search(
                r'^(?:.*[^0-9])([0-9]+)\sfiche',
                harvest['notes']
                )
            if r:
                self.resources = int(r[1])

        if 'notes' in harvest and restricted_to is None:
            for e in ('lots', 'jeux de données'):
                if "limité aux {}.".format(e) in harvest['notes']:
                    self.restricted_to = e
            # si non trouvé, on considèrera dans les
            # statistiques qu'il ne s'agissait pas
            # d'un moissonnage restreint

        if 'config' in harvest and ogc_filter is None:
            j = json.loads(harvest['config'])
            if 'ogcfilter' in j:
                self.ogc_filter = OgcFilter(j['ogcfilter'])               


class OgcFilter(list):
    """Classe pour les filtres OGC (filter encoding).

    Parameters
    ----------
    raw_filter : list of list
        Une liste de listes correspondant à un filtre OGC.
    
    """

    def __init__(self, raw_filter=None):
        if raw_filter:
            self += raw_filter

    def csw_matches(self, url_csw, maxtrials=30, strict=False):
        """Dénombre les fiches de métadonnées renvoyées par le filtre sur un CSW.

        Parameters
        ----------
        url_csw : str
            URL du serveur CSW sans aucun paramètre. Il n'est pas
            nécessaire que cette URL soit répertoriée dans le
            répertoire des CSW.
        maxtrials : int, default 30
            Nombre maximal de tentatives d'interrogation du serveur
            avant que la fonction ne se résolve à renvoyer une erreur.
        strict : bool, default False
            Si True, la fonction renvoie une erreur quand le serveur
            retourne une erreur.
        
        Returns
        -------
        int
            Nombre de fiches.
        
        """
        while maxtrials:
            maxtrials -= 1
            try:
                csw = CatalogueServiceWeb(url_csw)
                csw.getrecords2(parse_constraints(self))
                return csw.results['matches']
            except Exception as err:
                if strict:
                    raise err
                continue        
        

class CswImportError(Exception):
    """Erreur à la création d'un enregistrement dans le répertoire des serveurs CSW.

    """

class HarvestImportError(Exception):
    """Erreur à la création d'un enregistrement dans le répertoire des moissonnages.

    """

class OrgImportError(Exception):
    """Erreur à la création d'un enregistrement dans le répertoire des organisations.

    """

def apiannuaire_get(org_type):
    """Interroge l'API Annuaire pour un type d'établissement donné.

    Parameters
    ----------
    org_type : str
        Un type d'établissement. `org_type` devrait appartenir à
        :py:data:`ref_org_types` pour avoir une chance d'être reconnu.

    Returns
    --------
    list of dict
        Une liste de descriptifs d'organisations du type demandé.
    
    """
    res = requests.get("{}/v3/organismes/{}".format(apiep_url, org_type))
        
    if not res.status_code == 200:
        return None
    
    d = res.json()

    if not d or not d.get('features'):
        return None
    
    return d['features'][0]


def exists_url(url):
    """Contrôle la validité d'un lien.

    Parameters
    ----------
    url : str
        Un lien à tester.

    Returns
    -------
    bool
        False si une requête sur le lien provoque une erreur,
        True sinon.
        
    """
    res = requests.get(url)
    return res.status_code == 200


def org_type_from_name(name):
    """Renvoie le type d'une organisation, déduit de son nom.

    Parameters
    ----------
    name : str
        L'identifiant de l'organisation. Correspond à l'attribut
        :py:attr:`OrgRecord.name` et clé du répertoire des
        organisations, mais il n'est pas indispensable que
        l'organisation soit répertoriée.

    Returns
    -------
    str
        La fonction ne renvoie rien si le type n'est pas
        identifiable, ou ne fait pas partie de la liste de
        référence, :py:data:`ref_org_types`.
    
    """
    if name.startswith("administration-centrale-ou-ministere"):
        return "administration-centrale-ou-ministere"
    
    t = re.search('^([^-]+)[-]', name)
    if t and t[1] in ref_org_types:
        return t[1]


def extract_keywords(label_part):
    """Transforme une chaîne de caractères en liste de mots-clés.

    Parameters
    ----------
    label_part : str
        Une chaîne de caractères pouvant être un morceau de
        libellé d'organisation.

    Returns
    -------
    list of str
        Mots-clés extraits du libellé.
    
    """
    keep = ['Or']
    drop = ['des']
    
    keywords = re.split(r"\s|[-]|[']", label_part)
    for k in keywords.copy():
        if ( len(k) < 3 and not k in keep ) \
           or k in drop:
           keywords.remove(k)
    return keywords
    

def clean_label(label, org_type=None, sep=' - '):
    """Supprime du libellé les mentions indésirables.

    Parameters
    ----------
    label : str
        Le libellé d'une organisation. Correspond à l'attribut
        :py:attr:`OrgRecord.label` du répertoire des
        organisations, mais il n'est pas indispensable que
        l'organisation soit répertoriée.
    org_type : str, optional
        Le type d'établissement, parmi :py:data:`ref_org_types`.
        Si non fourni, la fonction considère que l'établissement
        n'est pas une division territoriale.
    sep : str, default ' - '
        Séparateur à utiliser entre les différents éléments du
        libellé. La valeur par défaut, ``' - '`` est ce qui
        utilisé par lannuaire.service-public.fr.

    Returns
    -------
    str
        Le libellé nettoyé. Concrètement, si le libellé est de la
        forme ``"[A] - [B] - [C]"``, la fonction supprime ``" - [C]"``,
        sauf si `org_type` montre que l'établissement est une division
        territoriale.

    Examples
    --------
    >>> clean_label("Direction interrégionale de la mer (DIRM) - Manche-Est, Mer-du-Nord")
    'Direction interrégionale de la mer (DIRM) - Manche-Est, Mer-du-Nord'
    
    >>> clean_label("Direction régionale de l'environnement, de l'aménagement" \
    ...     " et du logement (DREAL) - Occitanie - Siège de Toulouse")
    'Direction régionale de l'environnement, de l'aménagement et du logement (DREAL) - Occitanie'
    
    """
    maxelem = 3 if org_type == 'utea' else 2
    l = re.split("\s+-\s+", label)
    l = l[0:maxelem] if len(l) > maxelem else l
    return sep.join(l)


def split_label(label, org_type=None):
    """Renvoie une liste composée du type d'organisation et du secteur géographique.

    Parameters
    ----------
    label : str
        Le libellé d'une organisation. Correspond à l'attribut
        :py:attr:`OrgRecord.label` du répertoire des
        organisations, mais il n'est pas indispensable que
        l'organisation soit répertoriée.
    org_type : str, optional
        Le type d'établissement, parmi :py:data:`ref_org_types`.
        Si non fourni, la fonction considère que l'établissement
        n'est pas une division territoriale.

    Returns
    -------
    list
        Une liste avec :
        
        * ``[0]`` le type d'organisation.
        * ``[1]`` le secteur géographique de compétence.
        * ``[2]`` le cas échéant, le nom de la division territoriale.

    Examples
    --------
    >>> split_label("Direction départementale des territoires et " \
    ...     "de la mer (DDTM) - Seine-Maritime")
    ['Direction départementale des territoires et de la mer (DDTM)', 'Seine-Maritime']
    
    """
    maxelem = 3 if org_type == 'driea_ut' else 2
    l = re.split("\s+-\s+", label)
    return l[0:maxelem] if len(l) > maxelem else l
    
    
def clean_name(name):
    """Normalise un identifiant d'organisation suivant les critères de CKAN.

    Parameters
    ----------
    name : str
        Un futur identifiant d'organisation (paramètre `name` des dictionnaires
        envoyés à l'API CKAN).

    Returns
    --------
    str
        L'identifiant normalisé.

    Si `name` respectait déjà la forme attendue par l'API de CKAN (entre
    2 et 100 caractères, seulement des minuscules et des chiffres, ``-``
    et ``_``), il est renvoyé tel quel. Sinon les espaces et caractères spéciaux
    sont remplacés par des tirets ``-``, tout est mis en minuscules, et le
    nom est tronqué à 100 caractères.

    Examples
    --------
    >>> clean_name('abc-def')
    'abc-def'
    
    >>> clean_name('ABC DEF!')
    'abc-def-'
    
    >>> len(clean_name('x'*200))
    100
    
    """
    if name is None or len(name) < 2:
        return
    
    if re.fullmatch("[a-z0-9_-]{2,100}", name):
        return name
    
    cname = re.sub("[^a-z0-9_-]", "-", name.lower())
    if len(cname) > 100:
        cname = cname[0:100]
    return cname


def format_filter(filter_elements, format_function):
    """Applique la fonction de formatage au fragment de filtre.

    Parameters
    ----------
    filter_elements : OgcFilter or list of list
        Un filtre OGC ou un fragment de filtre OGC.
    format_function : function
        La fonction de formatage à utiliser pour les conditions
        ``PropertyIsLike``.

    Returns
    -------
    OgcFilter or list of list
        Un filtre OGC ou fragment de filtre, selon l'argument en entrée.
    
    """
    if filter_elements and isinstance(filter_elements[0], str):
        if filter_elements[0] == "PropertyIsLike":
            return [
                filter_elements[0],
                filter_elements[1],
                format_function(filter_elements[2])
                ]
        if filter_elements[1] == "PropertyIsLike":
            return [
                filter_elements[0],
                filter_elements[1],
                filter_elements[2],
                format_function(filter_elements[3])
                ]
        return filter_elements
    else:
        l = [ format_filter(e, format_function) \
            for e in filter_elements ]
        return OgcFilter(l) if isinstance(filter_elements, OgcFilter) \
            else l


def distribute(ogc_filter, base_filter):
    """Combine (AND) un fragment de filtre avec un filtre OGC.

    Parameters
    ----------
    ogc_filter : OgcFilter
        Un filtre OGC.
    base_filter : list of list of str
        Une liste de conditions élémentaires

    Returns
    -------
    OgcFilter
        Un filtre OGC.
    
    """
    if not ogc_filter:
        return base_filter
    if not base_filter:
        return ogc_filter

    f = OgcFilter()

    for e in ogc_filter:
        
        if isinstance(e[0], str):
            f.append([e] + base_filter)
        else:
            f.append(e + base_filter)
    
    return f


def validate(ogc_filter, operators):
    """Vérifie que le filtre OGC n'inclut que des opérateurs autorisés.

    Cette fonction suppose un filtre complètement développé.

    Parameters
    ---------
    ogc_filter : OgcFilter
        Un filtre OGC.
    operators : list of str
        La liste des opérateurs autorisés.

    Returns
    -------
    bool
        True si la validation est concluante, False sinon.
    
    """
    if len(ogc_filter) > 1 and not "OR" in operators:
        return False
    
    for e in ogc_filter:
        
        if isinstance(e[0], str):
            if e[0].upper() == 'NOT' and not "NOT" in operators:
                return False
        else:           
            if not "AND" in operators:
                return False
            
            for ee in e:
                if isinstance(ee[0], str):
                    if ee[0].upper() == 'NOT' and not "NOT" in operators:
                        return False
                else:
                    raise ValueError("Filtre OGC mal formé : {}.".format(ogc_filter))
    
    return True
