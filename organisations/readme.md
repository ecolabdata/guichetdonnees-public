# Gestion des organisations et des moissonnages

[Le répertoire des organisations](#le-répertoire-des-organisations) • [Le répertoire des moissonnages](#le-répertoire-des-moissonnages) • [Le répertoire des serveurs CSW](#le-répertoire-des-serveurs-csw) • [Le fichier des statistiques](#le-fichier-des-statistiques) • [Maintenance des répertoires](#maintenance-des-répertoires) • [Répercuter les changements sur les instances CKAN](#répercuter-les-changements-sur-les-instances-ckan) • [Syntaxe des filtres](#syntaxe-des-filtres)

## Le répertoire des organisations

Le fichier [organisations.json](/organisations/organisations.json) est le **répertoire des organisations**, soit l'export JSON d'un dictionnaire dont :
- les clés sont des identifiants d'organisations, identiques à la clé `name` évoquée ci-après ;
- les valeurs sont des dictionnaires contenant la configuration à fournir à l'API CKAN pour créer l'organisation (argument `data_dict` attendu par [`ckan.logic.action.create.organization_create`](https://docs.ckan.org/en/2.9/api/#ckan.logic.action.create.organization_create) et [`ckan.logic.action.update.organization_update`](https://docs.ckan.org/en/2.9/api/#ckan.logic.action.update.organization_update)).

Ce fichier a été initialisé à partir de l'[API Annuaire des établissements publics de l'administration](https://api.gouv.fr/documentation/api_etablissements_publics) (cf. [Mettre à jour ou importer des organisations avec l'API Annuaire Service-Public](#mettre-à-jour-ou-importer-des-organisations-avec-lapi-annuaire-service-public)), mais les nouvelles entrées devraient plutôt être ajoutées manuellement à l'avenir.

### Paramètres obligatoires

| Nom | Type | Obligatoire pour CKAN | Obligatoire pour la gestion des organisations | Description |
| --- | --- | --- | --- | --- |
| `name` | str | oui | oui | L'identifiant de l'organisation (toujours identique à la clé), tel qu'utilisé par l'annuaire de Service-Public.fr. À noter que CKAN requiert 2 à 100 caractères alpha-numériques minuscules + `'_'` et `'-'`. CKAN l'utilise notamment pour constituer les URL : https://data.developpement-durable.gouv.fr/organization/about/name pointe sur la page de description de l'organisation et https://data.developpement-durable.gouv.fr/organization/name pointe sur la liste de ses datasets. |
| `title` | str | oui | non | Libellé court de l'organisation - c'est celui que CKAN utilise pour nommer l'organisation. Il doit nécessairement être présent lorsque le contenu du répertoire des organisations est soumis à l'API, cependant le système de gestion des organisations est capable de le déduire de la propriété `label` ci-après, donc il n'est pas nécessaire de le spécifier au départ (cf. [Ajouter ou modifier une organisation](#ajouter-ou-modifier-une-organisation)). |
| `label` | str | non | oui | Libellé long de l'organisation. Cette information n'est pas utilisée par CKAN, par contre elle est essentielle au système de gestion des organisations. Cf. ci-après pour la syntaxe. |

#### Syntaxe de `name`

L'identifiant - `name` - doit de préférence être le véritable identifiant de l'organisation dans l'annuaire de Service-Public.fr. À défaut, il est essentiel qu'il soit formé de la même manière et ne soit pas l'identifiant d'une autre organisation dans l'annuaire de Service-Public.fr.

Pour une administration centrale : le préfixe `"administration-centrale-ou-ministere_"` suivi de six chiffres.

Pour un service déconcentré :
- un préfixe correspondant au type de service, parmi `"ddt"` (DDT et DDTM), `"dreal"` (DREAL), `"driea"` (DRIEAT Île-de-France), `"driea_ut"` (unités départementales de la DRIEAT Île-de-France), `"drihl"` (DRIHL Île-de-France), `"dir_mer"` (DIRM), `"did_routes"` (DIR), `"dreal_ut"` (DEAL ou unités départementales de DREAL), `"dtam"` (DTAM Saint-Pierre-et-Miquelon). D'autres valeurs pourront être ajoutées ultérieurement ;
- un tiret `"-"` ;
- le code INSEE de la commune (principale) d'implantation du service ;
- un tiret `"-"` ;
- un numéro d'ordre sur deux chiffres.

*En pratique, tous les services déconcentrés des types susmentionnés font partie du répertoire, sauf les unités départementales de DREAL. Tous les identifiants utilisés sont repris de l'annuaire de Service-Public.fr, à l'exception des deux DDT de Corse, qui pour une raison mystérieuse n'y figurent pas.*

#### Syntaxe de `label`

Le libellé long - `label` - doit être composé comme suit :
- nom du service en toutes lettres (sans le territoire de compétence). Ex : "*Direction régionale et interdépartementale de l'environnement, de l'aménagement et des transports*".
- un espace, puis, entre parenthèses, le sigle correspondant. Ex : " *(DRIEAT)*".
- le cas échéant, le territoire de compétence en toutes lettres, séparé de ce qui précède par un tiret. Ex : " *- Île-de-France*".
- le cas échéant, le nom de la division territoriale en toutes lettres avec son territoire de compétence, séparé de ce qui précède par un tiret. Ex : " *- Unité départementale de Seine-Saint-Denis*".

Exemples : "*Direction de l'environnement, de l'aménagement et du logement (DEAL) - Mayotte*" (cas d'un service déconcentré lambda), "*Direction régionale et interdépartementale de l'environnement, de l'aménagement et des transports (DRIEAT) - Île-de-France - Unité départementale de Seine-Saint-Denis*" (cas d'une division territoriale), "*Commissariat général au développement durable (CGDD)*" (cas d'une administration centrale). 

### Paramètres optionnels

| Nom | Type | Description |
| --- | --- | --- |
| `description` | str | Descriptif de l'organisation. À noter que CKAN prend en charge le Markdown sur ce champ (probablement de manière assez basique).|
| `image_url` | str | URL du logo de l'organisation. |
| `groups` | list | Liste de dictionnaires (en fait jamais plus d'un), dont l'unique clé, `'name'` fournit l'identifiant de l'organisation dont l'organisation considérée fait partie. Exemple : `[{"name": "administration-centrale-ou-ministere_172120"}]`. |

Les descriptifs sont à ce stade des copier-coller légèrement métaphrasés des décrets qui définissent les missions des services (cf. [Importer une description standard](#importer-une-description-standard)), qui auront vocation à être améliorés et/ou personnalisés par la suite. Ils sont propres à l'organisation dans le cas des services d'administration centrale, ou constitués à partir d'une trame commune à toutes les organisations du type pour les services déconcentrés. Ces trames se trouvent dans le fichier [descriptifs_basiques.json](/organisations/utils/descriptifs_basiques.json).

Les logos se trouvent en principe dans le répertoire `organisations/logos` du Git [guichetdonnees-publics](https://github.com/ecolabdata/guichetdonnees-public/tree/main/organisations/logos) et sont nommés d'après l'identifiant ou le type de l'organisation.

Il existe d'autres paramètres optionnels, qui pourraient éventuellement être utilisés, mais ne sont a priori pas pertinent ici. Cf. [documentation de `ckan.logic.action.create.organization_create`](https://docs.ckan.org/en/2.9/api/#ckan.logic.action.create.organization_create).

### Métadonnées complémentaires

Les métadonnées complémentaires sont contenues dans la clé `extras`, dont la valeur est une liste de dictionnaires `{ "key": "nom de la métadonnée", "value": "valeur de la métadonnée" }`.

Les métadonnées suivantes peuvent être présentes, selon leur disponibilité dans les informations exposées par l'[API Annuaire des établissements publics
de l'administration](https://api.gouv.fr/documentation/api_etablissements_publics) :

| Nom (key) | Description |
| --- | --- |
| `Courriel` | Adresse mél ou URL d'une page de contact |
| `Téléphone` | Numéro de téléphone |
| `Site internet` | URL du site de l'organisation |

Il est évidemment possible d'en ajouter d'autres.

### Configuration des moissonnages associés à l'organisation

En sus du fichier principal [organisations.json](/organisations/organisations.json), le fichier annexe [organisations_config.json](/organisations/organisations_config.json) peut être utilisé pour personnaliser la configuration des moissonnages de l'organisation, s'il y a lieu. Une telle personnalisation n'est pas utile dans le cas générale, mais elle devient nécessaire quand il n'est pas possible de déduire automatiquement du nom de l'organisation le filtre à utiliser pour récupérer les fiches de l'organisation exposées par les serveurs CSW.

*NB : pour définir manuellement le filtre à utiliser pour l'organisation sur un serveur donné, on utilisera le paramètre `bypass` du [répertoire des serveurs CSW](#répertoire-des-serveurs-csw) et non les paramètres ci-après, qui s'appliquent indifféremment à tous les serveurs.*

Le fichier [organisations_config.json](/organisations/organisations_config.json) sert uniquement à la constitution du [répertoire des moissonnages](#répertoire-des-moissonnages), il n'est pas destiné à l'API CKAN.

Dans ce document, les clés sont les identifiants des organisations, présumées déjà répertoriées dans [organisations.json](/organisations/organisations.json) (sinon elles n'auront aucun effet).

Les paramètres suivants peuvent être spécifiés :

| Nom | Type | Description |
| --- | --- | --- |
| `frequency` | str | Fréquence de moissonnage pour l'organisation. Si elle est renseignée, elle prévaut sur la fréquence définie pour le serveur CSW (cf. [Répertoire des serveurs CSW](#répertoire-des-serveurs-csw)). Valeurs autorisées : `'MANUAL'`, `'MONTHLY'`, `'WEEKLY'`, `'BIWEEKLY'`, `'DAILY'`, `'ALWAYS'` (cf. [code de ckan-harvest](https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py)). | 
| `base_filter` | list | Une liste de conditions élémentaires à combiner (`AND`) systématiquement à tout filtre défini pour l'organisation - cf. [Syntaxe des filtres](#syntaxe-des-filtres). À noter que si les conditions font appel à l'opérateur `NOT` et que celui-ci n'est pas pris en charge par le serveur, aucun moissonnage ne sera défini. |
| `add_filter` | OgcFilter | Un filtre OGC à ajouter (`OR`) aux filtres définis automatiquement pour les moissonnages de l'organisation (sous réserve que l'opérateur `OR` soit bien pris en charge par le serveur et que tous les opérateurs utilisés par le filtre soient également pris en charge, sinon `add_filter` est ignoré). Si aucun filtre automatique ne renvoie de résultat, c'est le filtre additionnel qui sera utilisé. Les filtres additionnels sont automatiquement combinés avec le `base_filter` du CSW (cf. [Répertoire des serveurs CSW](#répertoire-des-serveurs-csw)), mais sont présumés déjà inclure le `base_filter` de l'organisation s'il y avait lieu. |
| `bypass_all` | OgcFilter | S'il y a lieu, le filtre OGC à utiliser - cf. [Syntaxe des filtres](#syntaxe-des-filtres) - pour tous les moissonnages de l'organisation. À noter que les filtres des attributs `bypass` des serveurs prévalent sur `bypass_all` (cf. [Répertoire des serveurs CSW](#répertoire-des-serveurs-csw)). `bypass_all` est présumé inclure les conditions du `base_filter` de l'organisation s'il y avait lieu. Il sera automatiquement combiné avec le `base_filter` du CSW. Si `bypass_all` fait appel à des opérateurs non pris en charge par un serveur CSW, aucun moissonnage ne sera défini pour ce serveur. |
| `include` | list | S'il y a lieu, une liste fermée des serveurs CSW (`url`) pour lesquels des moissonnages peuvent être créés (liste blanche). Si cet attribut n'est pas défini, il sera considéré que tous les serveurs sont autorisés. |
| `exclude` | list | S'il y a lieu, liste d'identifiants de serveurs CSW (`url`) pour lesquels aucun moissonnage ne doit être défini (liste noire). |

Que ce soit pour `base_filter`, `add_filter` et `bypass_all`, les valeurs de `PropertyIsLike` ne doivent jamais être encadrées de `'%'`. Ils seront ajoutés ou non selon ce qui est préférable pour le serveur considéré.


## Le répertoire des moissonnages

Le fichier [moissonnages.json](/organisations/moissonnages.json) est le **répertoire des moissonnages**, soit l'export JSON d'un dictionnaire dont :
- les clés sont des identifiants des moissonnages, composés de l'identifiant - `name` - de l'organisation et d'un numéro d'ordre ;
- les valeurs sont des dictionnaires contenant la configuration à fournir à l'API CKAN pour créer le moissonnage (argument `data_dict` attendu par [`ckanext.harvest.logic.action.create.harvest_source_create`](https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/logic/action/create.py) et [`ckanext.harvest.logic.action.update.harvest_source_update`](https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/logic/action/update.py)).

**ATTENTION ! Ce fichier ne doit pas être modifié manuellement, les changements réalisés ne seraient pas pérennes. Cf. [Générer les moissonnages](#générer-les-moissonnages) pour la marche à suivre.**

L'ordre dans lequel les moissonnages apparaissent dans ce fichier est l'inverse de l'ordre dans lequel ils seront réalisés par CKAN.

À titre d'information, les paramètres sont :

| Nom | Type | Description |
| --- | --- | --- |
| `url` | str | URL du serveur CSW moissonné, sans aucun paramètre. Ex : `"https://inspire.ternum-bfc.fr/geonetwork/srv/fre/csw"`. |
| `name` | str | L'identifiant du moissonnage, identique à la clé. |
| `owner_org` | str | L'identifiant de l'organisation - `name` - à laquelle seront attribuées les fiches de métadonnées moissonnées. |
| `title` | str | Le libellé explicite du moissonnage, constitué du libellé (`title`) du serveur et du libellé (`title`) de l'organisation. |
| `notes` | str | Un commentaire libre. En pratique, il contient la date de calcul du moissonnage et le nombre de fiches de métadonnées qu'il est supposé récupérer. |
| `source_type` | str | Le type de moissonnage, parmi les types pris en charge. À ce stade, il vaut toujours 'csw'. |
| `frequency` | str | La fréquence du moissonnage, parmi `'MANUAL'`, `'MONTHLY'`, `'WEEKLY'`, `'BIWEEKLY'`, `'DAILY'`, `'ALWAYS'` (cf. [code de ckan-harvest](https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py)). |
| `config` | str | La sérialisation JSON du dictionnaire contenant la configuration du moissonnage à proprement parler. |

`config` contient lui-même les paramètres :

| Nom | Type | Description |
| --- | --- | --- |
| `maxtrials` | int | Nombre maximal de tentatives d'interrogation du serveur avant échec du moissonnage. Il vaut généralement `5`, parfois plus pour des serveurs sur lesquels des dysfonctionnements ont été identifiés. |
| `ogcfilter` | list | Le filtre à utiliser lors du moissonnage pour n'obtenir que les fiches de métadonnées de l'organisation considérée. |
| `default_extras` | dict | Dictionnaire clé-valeur - `{ "Nom propriété 1": "Valeur propriété 1", "Nom propriété 2": "Valeur propriété 2" }` - contenant des métadonnées à ajouter à toutes les fiches moissonnées. Concrètement, il s'agit ici d'ajouter l'information "Catalogue source", avec le nom du catalogue et son URL. |


## Le répertoire des serveurs CSW

Le fichier [serveurs_csw.json](/organisations/serveurs_csw.json) est le **répertoire des serveurs CSW**, soit l'export JSON d'un dictionnaire dont :
- les clés sont les URL des points de moissonnage (sans aucun paramètre) ;
- les valeurs sont des dictionnaires contenant divers éléments caractéristiques du serveur.

Contrairement aux répertoires des organisations et répertoire des moissonnages, le répertoire des serveurs CSW ne sert pas au dialogue avec l'API CKAN, mais uniquement à constituer le répertoire des moissonnages.

Tout nouveau point de moissonnage doit être déclaré manuellement dans ce fichier.

### Paramètres obligatoires

| Nom | Type | Description |
| --- | --- | --- |
| `title` | str | Le libellé du serveur. |
| `kind` | str | Le type de serveur. Actuellement, les valeurs utilisées sont `'geoide'` et `'geonetwork'` et ce paramètre détermine si les chaînes de caractères argument de `PropertyIsLike` doivent (pour `'geonetwork'`) ou non (pour `'geoide'`) être encadrées de `'%'`. |
| `page` | str | L'URL d'accès grand public au catalogue. |

### Paramètres optionnels

| Nom | Type | Description |
| --- | --- | --- |
| `frequency` | str | Fréquence de moissonnage. Valeurs autorisées : `'MANUAL'`, `'MONTHLY'`, `'WEEKLY'`, `'BIWEEKLY'`, `'DAILY'`, `'ALWAYS'` (cf. [code de ckan-harvest](https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py)). À noter qu'il est aussi possible de définir d'associer des fréquences aux organisations, lesquelles prévaudront sur cette valeur. | 
| `base_filter` | list | Une liste de conditions élémentaires à combiner (`AND`) systématiquement à tout filtre défini sur le serveur - cf. [Syntaxe des filtres](#syntaxe-des-filtres). À noter que si les conditions font appel à l'opérateur `NOT` et que celui-ci n'est pas pris en charge par le serveur, aucun moissonnage ne sera défini. |
| `bypass` | dict | S'il y a lieu, dictionnaire dont les clés sont des identifiants d'organisations - `name` - et les valeurs les filtres OGC à utiliser pour les moissonnages du patrimoine de ces organisations sur le serveur. Cf. [Syntaxe des filtres](#syntaxe-des-filtres). Ces filtres sont présumés déjà inclure les conditions de `base_filter` (s'il y a lieu) et ne pas faire appel à des opérateurs qui ne seraient pas pris en charge par le serveur (pas de contrôle). |
| `include` | list | S'il y a lieu, une liste fermée des identifiants d'organisations - `name` - pour lesquelles des moissonnages peuvent être créés (liste blanche). Si cet attribut n'est pas défini, il sera considéré que toutes les organisations sont autorisés. |
| `exclude` | list | S'il y a lieu, liste des identifiants d'organisations - `name` - pour lesquelles aucun moissonnage ne doit être défini (liste noire). |
| `maxtrials` | int | Nombre maximal de tentatives d'interrogation du serveur avant échec du moissonnage. Si non renseigné, il sera fixé à `5`. |
| `operators` | str | La liste des opérateurs autorisés pour les filtres. Il n'est pas nécessaire d'indiquer `["AND", "OR", "NOT"]` quand tous les opérateurs sont pris en charge, c'est ce qui est considéré par défaut. **A minima, `AND` doit être pris en charge**. |
| `restriction` | dict | Ce paramètre sert à établir des moissonnages différenciés pour une même organisation sur un même serveur, par exemple pour moissonner d'abord les lots (premier moissonnage avec un filtre sur les lots) puis les jeux de données (second moissonnage avec un filtre sur les jeux de données). Il s'agit d'un dictionnaire dont les clés correspondent aux libellés des critères de différenciation et les valeurs sont des listes de conditions élémentaires qui seront combinées (`AND`) aux filtres distinguant les jeux de données de l'organisation - cf. [Syntaxe des filtres](#syntaxe-des-filtres). **Attention : l'ordre des clés est l'inverse de l'ordre dans lequel les moissonnages devront être réalisés.** Ex : `{"lots": [["PropertyIsLike", "Identifier", "fr-120066022-ldd-%"]], "jeux de données": [["PropertyIsLike", "Identifier", "fr-120066022-jdd-%"]]}`. |

### Ordre de moissonnage des serveurs

Considérant que les catalogues se moissonnent souvent entre eux et que la gestion des identifiants - `name` - des jeux de données par CKAN est telle que le jeu ne sera pas importé si son identifiant (déduit de `FileIdentifier`) est déjà présent, il est généralement préférable de moissonner en premier les CSW qui :
- n'en moissonnent pas d'autres ;
- sont moissonnés par d'autres.

En pratique, le fichier [serveurs_csw_ordre.json](/organisations/serveurs_csw_ordre.json) liste les serveurs dans l'ordre où ils doivent être moissonnés. Les moissonnages sur des serveurs qui n'apparaissent pas dans ce fichier seront réalisés à la fin, dans un ordre aléatoire.


## Le fichier des statistiques

Le fichier [statistiques.md](/organisations/statistiques.md) donne une vision synthétique et plus adaptée à une lecture par un être humain du contenu des répertoires. Il liste notamment les moissonnages mis en place pour chaque organisation et pour chaque catalogue, avec le nombre de fiches qu'ils sont supposés apporter.


## Maintenance des répertoires

Les fonctions de maintenance des répertoires sont fournies par [admin.py](/organisations/admin.py).

Avant toute opération, il est nécessaire de charger les répertoires, en générant un objet `MetaCollection`:
```python
mC = MetaCollection()
```

Cet objet a quatre attributs :
- `org` est le répertoire des organisations (classe `OrgCollection`) ;
- `harvest` est le répertoire des moissonnages (classe `HarvestCollection`) ;
- `csw` est le répertoire des serveurs CSW (classe `CswCollection`) ;
- `statistics` est le fichier des statistiques (classe `Statistics`).

Il est possible d'intervenir indépendamment sur chacun de ces objets, qui disposent chacun de leurs propres méthodes (définies et documentées dans [admin.py](/organisations/admin.py)), mais il reste préférable d'utiliser les méthodes de la classe `MetaCollection`, présentée dans la suite, qui prennent mieux en compte leurs interactions. Par exemple, la méthode de génération de descriptifs `write_basic_metadata` de `MetaCollection` va non seulement exécuter la méthode de même nom d'`OrgCollection`, mais aussi mettre à jour le fichier des statistiques, qui recense les organisations sans descriptif.

Il reste intéressant de savoir que chaque répertoire ou fichier peut être sauvegardé indépendamment :

```python
mC = MetaCollection()

# sauvegarder le répertoire des organisations,
# le répertoire des moissonnages et le fichier
# des statistiques :
mC.save()

# sauvegarder le répertoire des organisations seul :
mC.org.save()

# sauvegarder le répertoire des moissonnages seul :
mC.harvest.save()

# sauvegarder le fichier des statistiques seul :
mC.statistics.export()
```

*Il n'existe pas de méthode pour sauvegarder le répertoire des serveurs CSW, car aucun des mécanismes définis dans [admin.py](/organisations/admin.py) n'a pour effet de le modifier.*

### Ajouter ou modifier une organisation

La création d'une organisation se fait généralement à la main dans le fichier [organisations.json](/organisations/organisations.json), en spécifiant au moins l'identifiant de l'organisation - `name` - et son libellé long - `label`. Cf. [Répertoire des organisations](#paramètres-obligatoires).

Il est également possible d'importer des organisations avec l'API Annuaire Service-Public, comme évoqué [plus loin](#mettre-à-jour-ou-importer-des-organisations-avec-lapi-annuaire-service-public).

Le seul fait de charger le répertoire des organisations a pour effet de générer la clé `title` si elle n'avait pas été renseignée[^title-et-label], et de mettre à jour le fichier des statistiques :

```python
mC = MetaCollection()
mC.save()
```

[^title-et-label]: La clé `title` n'est par contre pas recalculée quand `label` est modifié (car il est admis que `title` puisse être saisie manuellement). Pour forcer la mise à jour, il faudra effacer `title` en parallèle des changements sur `label`.

Comme évoqué plus loin, [admin.py](/organisations/admin.py) propose aussi des méthodes pour [le descriptif](#importer-une-description-standard) et [le logo](#spécifier-le-logo).

### Ajouter ou modifier un serveur CSW

Les serveurs CSW sont à déclarer à la main dans le fichier [serveurs_csw.json](/organisations/serveurs_csw.json). Cf. [Répertoire des serveurs CSW](##le-répertoire-des-serveurs-csw). Toute modification de ce fichier suppose de régénérer ensuite tous les moissonnages pour les serveurs considérés (voir [ci-après](#générer-les-moissonnages)).

### Générer les moissonnages

`build_harvest_sources` est la méthode de la classe `MetaCollection` qui permet de mettre à jour le fichier des moissonnages.

Si elle est lancée sans aucun paramètre, elle passera en revue toutes les organisations et tous les serveurs CSW, tentant de produire un filtre qui :
1. soit le plus large possible, pour maximiser les chances de récupérer l'intégralité du patrimoine de l'organisation et rendre le filtre moins sensible aux potentielles évolutions du nom[^changement-nom]. Cet objectif est difficilement atteignable pour un serveur qui ne prend pas en charge l'opérateur `OR` - dans ce cas, la fonction se contentera de chercher un filtre qui fournisse un résultat ;
2. reste discriminant, car il n'est pas question que le filtre ramène des fiches appartenant à d'autres organisations. Pour les serveurs qui ne prennent pas en charge l'opérateur `NOT`, ce n'est pas nécessairement possible pour toutes les organisations. En cas d'échec, la fonction renoncera à définir un moissonnage ;
3. permette effectivement de récupérer des fiches de l'organisation sur le serveur. Autrement dit, aucun moissonnage ne sera créé si le filtre ne renvoie rien (vraisemblablement parce que l'organisation n'a pas de fiches sur le serveur).

[^changement-nom]: Ceci ne suffira certainement pas si le nom officiel de l'organisation change. Il s'agit surtout de prendre en compte les cas où un nom de département serait remplacé par un code, un sigle par un libellé en toutes lettres, etc.

```python
mC = MetaCollection()
mC.build_harvest_sources()
mC.save()
```

Cette opération pouvant prendre plusieurs dizaines de minutes, on préférera souvent restreindre le périmètre à traiter grâce aux arguments ci-après (qui peuvent tout à fait être utilisés ensemble) :
- `org_name` permet de spécifier l'identifiant de l'organisation pour laquelle les moissonnages doivent être générés, ou une liste d'identifiant d'organisations ;
- `url_csw` permet de spécifier l'URL du CSW pour lequel les moissonnages doivent être générés, ou une liste d'URL de CSW ;
- `org_name_exclude` est une liste d'identifiant d'organisations à exclure du traitement ;
- `url_csw_exclude` est une liste d'URL de CSW à exclure du traitement.

Par défaut, `build_harvest_sources` ignore les moissonnages licites[^licite] déjà définis. Pour les recontrôler et mettre à jour leurs statistiques, il faudra spécifier `replace=True` en argument.

[^licite]: Un moissonnage manifestement illicite - par exemple pour une organisation qui apparaît sur la liste noire du serveur - sera supprimé quoi qu'il arrive.


### Supprimer une organisation ou un serveur CSW

Serveurs et organisations peuvent être effacés à la main de leurs fichiers respectifs.

Il importe ensuite de supprimer les moissonnages orphelins avec :
```python
mC = MetaCollection()
mC.clean_harvest_sources()
mC.save()
```

### Importer une description standard

Pour certains types d'organisations, il est possible de générer automatiquement des descriptifs standard, qui listent simplement les missions du service[^trame].

[^trame]: Les trames de descriptions se trouvent dans le fichier [descriptifs_basiques.json](/organisations/descriptifs_basiques.json). Elles peuvent être éditées, auquel cas il faudra mettre à jour les descriptifs pour toutes les organisations des types concernés. Les balises `{label}` et `{title}` ont vocation à être remplacées par les valeurs des propriétés de mêmes noms du répertoire des organisations, `{area}` par le secteur géographique déduit du libellé et `{littoral}` par le texte spécifié par la clé `littoral` du fichier [descriptifs_basiques.json](/organisations/descriptifs_basiques.json), sous réserve que l'organisation soit identifiée comme "maritime" (ne fonctionne aujourd'hui que pour les DDTM).

Soit `my_org_name` le nom de l'organisation considérée. On procédera comme suit :

```python
mC = MetaCollection()
mC.write_basic_metadata(org_name=my_org_name)
mC.save()
```

S'il n'a pas été possible de générer le descriptif, car le type de l'organisation ne le permet pas, un message d'information apparaît dans la console. Il est dans ce cas nécessaire de saisir le descriptif à la main, dans la clé `'description'` du fichier [organisations.json](/organisations/organisations.json)

Il est également possible de mettre à jour les descriptifs pour toutes les organisations d'un même type avec :
```python
mC = MetaCollection()
mC.write_basic_metadata(org_type=my_org_type)
mC.save()
```

... ou même d'actualiser les descriptifs de toutes les organisations (laisse tels quels les descriptifs saisis manuellement pour les organisations sans descriptif standard, écrase les autres) :
```python
mC = MetaCollection()
mC.write_basic_metadata()
mC.save()
```

*En pratique, tous les services déconcentrés ont aujourd'hui des descriptifs standard, tandis que ceux des services d'administration centrale sont gérés à la main.*

Les organisations sans descriptif sont listées dans le fichier [statistiques.md](/organisations/statistiques.md#organisations-sans-descriptif). Cette liste est automatiquement mise à jour avec les commandes susmentionnées.

### Spécifier le logo

Dans l'absolu, il est possible de renseigner n'importe quelle URL dans la clé `image_url` du répertoire des organisations, mais [admin.py](/organisations/admin.py) propose une méthode générique pour définir un logo.

Le pré-requis est qu'il existe dans le répertoire `organisations/logos` du Git [guichetdonnees-publics](https://github.com/ecolabdata/guichetdonnees-public/tree/main/organisations/logos) une image au format PNG, JPG/JPEG ou SVG dont le nom est soit l'identifiant - `name` - de l'organisation, soit son type. S'il existe un logo pour le type et pour l'organisation, celui de l'organisation prévaut. Pour les services de l'Etat, les logos utilisés sont les bloc-marques officiels.

[admin.py](/organisations/admin.py) propose une méthode qui vérifie l'existence du fichier et écrit son URL dans le répertoire.

Pour mettre à jour le logo d'une seule organisation :
```python
mC = MetaCollection()
mC.get_logo(org_name=my_org_name)
mC.save()
```

Pour mettre à jour les logos de toutes les organisations d'un type :
```python
mC = MetaCollection()
mC.get_logo(org_type=my_org_type)
mC.save()
```

Pour mettre à jour les logos de toutes les organisations du répertoire :
```python
mC = MetaCollection()
mC.get_logo()
mC.save()
```

Si aucun logo n'a été trouvé pour une organisation, un message d'alerte apparaîtra dans la console.

Les organisations sans logo sont listées dans le fichier [statistiques.md](/organisations/statistiques.md#organisations-sans-logo). Cette liste est automatiquement mise à jour avec les commandes susmentionnées.

### Mettre à jour ou importer des organisations avec l'API Annuaire Service-Public

La méthode `add_from_apiannuaire` de la class `OrgCollection` permet de créer ou mettre à jour des organisations à partir de l'API [API Annuaire des établissements publics de l'administration](https://api.gouv.fr/documentation/api_etablissements_publics), qui met à disposition une partie des informations officielles du site [lannuaire.service-public.fr](https://lannuaire.service-public.fr/) (uniquement les services déconcentrées ou relevant des collectivités).

```python
mC = MetaCollection()
mC.org.add_from_apiannuaire()
...
mC.save()
```

Si elle est exécutée sans argument, `add_from_apiannuaire` interrogera l'API sur tous les types d'organisation pré-identifiés comme pertinents (ceux qui sont listés par la variable `ref_org_types` - cf. [explications ci-avant](#syntaxe-de-name)), mais il est possible de restreindre le traitement en spécifiant :
- un type ou une liste de types via `org_type` ;
- un identifiant ou une liste d'identifiants d'organisations via `org_name` (prévaut sur `org_type`).

Par exemple, pour ajouter d'hypothétiques DDT et DDTM manquantes :
```python
mC.org.add_from_apiannuaire(org_type='ddt')
```

Par défaut, la fonction se contente d'ajouter les organisations manquantes, sans toucher à celles qui existent déjà. Pour qu'elle mette à jour les métadonnées des organisations, il faudra ajouter l'argument `replace==True`. À noter que toute information saisie manuellement sera perdue lors de la mise à jour.

Par exemple, pour mettre à jour l'organisation DEAL Guyane :
```python
mC.org.add_from_apiannuaire(org_name="dreal_ut-97302-01", replace=True)
```

`add_from_apiannuaire` exécute d'elle-même `get_logo` et `write_basic_metadata`, mais il sera au moins nécessaire de lancer `build_harvest_sources` pour générer les moissonnages sur les nouvelles organisations créées, ou si le libellé de l'organisation a été modifié.


## Répercuter les changements sur les instances CKAN

Le fichier [dialog.py](/organisations/dialog.py) fournit les commandes nécessaires pour mettre à jour les organisations et moissonnages des instances CKAN en fonction des répertoires.

Avant toute opération, on chargera les informations nécessaires au dialogue avec les API des instances, en générant un objet `Ckan`:
```python
ckan = Ckan()
```

Dans le cas d'une connexion depuis le réseau interne du ministère, il faudra ajouter le paramètre `intranet=True` :
```python
ckan = Ckan(intranet=True)
```

Cet objet a un attribut par environnement :
- `dev` pour l'environnement de développement ;
- `preprod` pour la pré-production ;
- `prod` pour la production.

`ckan.dev`, `ckan.preprod` et `ckan.prod` sont eux-mêmes des objets de classe `CkanEnv` avec les attributs suivants :
- `name` est le nom de l'environnement ;
- `url` est l'URL de base de l'instance CKAN ;
- `api_token` contient le jeton d'API qui sera utilisé pour les requêtes ;
- `verify` est un booléean qui indique si la validité du certificat serveur doit être contrôlée. Il devrait toujours valoir `True`, sauf dans un cas où il est connu que les certificats utilisés sont invalides (ou auto-signés).
- `proxy` est un dictionnaire de paramétrage du proxy, renseigné uniquement dans le cas d'une connexion depuis le réseau interne du ministère.

Le jeton d'API est chargé depuis le fichier nommé `jeton_api_ckan_[dev/prod/preprod].txt` (suffixe variable selon l'environnement) qui doit se trouver dans le répertoire [jetons](/organisations/jetons). Cf. [readme.md](/organisations/jetons/readme.md).

*Les commandes évoquées dans la suite font appel à des méthodes de `CkanEnv`, qui sont donc à exécuter sur un environnement donné. Par commodité, les exemples utilisent l'environnement de développement, mais le fonctionnement serait identique pour les autres.*


### Appliquer les modifications du répertoire des organisations

On exécutera simplement :

```python
ckan = Ckan()
ckan.dev.refresh_orgs()
```

Cette commande :
- crée les organisations du répertoire qui n'existent pas encore sur l'instance CKAN, - - supprime celles qui n'existent plus dans le répertoire (après avoir pris soin de supprimer leurs moissonnages et jeux de données associés),
- met à jour les métadonnées des autres (sans se préoccuper de vérifier si elles ont été modifiées, car ce serait plus coûteux en temps de calcul et en volume de données transférées).


### Appliquer les modifications du répertoire des moissonnages

La commande est cette fois :

```python
ckan = Ckan()
ckan.dev.refresh_harvest_sources()
```

Comme `refresh_orgs` pour les organisations, cette commande met à jour les moissonnages qui existent à la fois dans le répertoire et sur l'instance, crée ceux qui manquent et supprime ceux qui ont disparu du répertoire (avec tous les jeux de données associés).

Les nouveaux moissonnages seront automatiquement exécutés à la prochaine activation du cron. Par défaut, les moissonnages existants ne sont *pas* relancés, sauf si `re_run=True` a été spécifié en argument, auquel cas anciens et nouveaux moissonnages sont immédiatement lancés, dans l'ordre prévu par le répertoire.

```python
ckan = Ckan()
ckan.dev.refresh_harvest_sources(re_run=True)
```

Relancer les moissonnages ralentit fortement l'exécution de la fonction, pour les mêmes raisons que présenté [ici](#exécuter-tous-les-moissonnages-dans-lordre).


### Actions ciblées

Les méthodes `org_action` et `harvest_action` permettent d'exécuter des commandes de création, mise à jour, etc. portant respectivement sur une organisation et un moissonnage. Elles prennent en charge à la fois la récupération des informations dans le répertoire et les requêtes sur l'API.

`action_request` peut être utilisée pour transmettre facilement une requête quelconque à l'API.

[dialog.py](/organisations/dialog.py) ajoute également quelques méthodes facilitatrices pour des requêtes courantes pour lesquelles il n'existe pas de commande d'API dédiée :
- `org_id_from_name` pour obtenir l'identifiant technique CKAN - `id` - à partir de la clé `name`, qui sert notamment d'identifiant pour le répertoire des organisations et apparaît dans les URL de CKAN.
- `harvest_id_from_name` est l'équivalent de la fonction précédente pour les moissonnages.
- `harvest_sources_list` permet de lister l'ensemble des moissonnages de l'instance considérée.
- `org_packages_list` liste les jeux de données d'une organisation.
- `harvest_packages_list` liste les jeux de données d'un moissonnage.
- `clear_all_dataset` permet de supprimer tous les jeux de données de l'instance ou, selon les arguments, ceux qui dépendent d'une organisation ou d'un moissonnage donné.
- `run_harvest_job` permet de relancer un moissonnage.
- `run_all_harvest_jobs` permet de relancer tous les moissonnages dans le bon ordre.

Quelques commandes courantes sont listées ci-après. On se reportera aux en-tête des fonctions dans [dialog.py](/organisations/dialog.py) pour plus de détails.


#### Ajouter une seule organisation

Soit `my_org_name` l'identifiant - `name` - de l'organisation dans le répertoire.

```python
ckan = Ckan()
ckan.dev.org_action('create', my_org_name)
```

Cette commande n'a pas pour effet de créer les moissonnages de l'organisation. Cf. [Ajouter un seul moissonnage](#ajouter-un-seul-moissonnage).

Si la fonction ne renvoie rien, l'opération a réussi.


#### Mettre à jour une seule organisation

Soit `my_org_name` l'identifiant - `name` - de l'organisation dans le répertoire.

```python
ckan = Ckan()
ckan.dev.org_action('update', my_org_name)
```

Cette commande n'affecte pas les moissonnages de l'organisation.

Si la fonction ne renvoie rien, l'opération a réussi.


#### Supprimer une seule organisation

La suppression des organisations passe par une fonction spécifique, `org_erase`, car elle implique plusieurs actions successives pour que tous les objets liés (moissonnages et jeux de données) soient également détruits et que les identifiants - `name` - redeviennent disponibles.

Soit `my_org_name` l'identifiant - `name` - de l'organisation dans le répertoire.

```python
ckan = Ckan()
ckan.dev.org_erase(my_org_name)
```

Si la fonction ne renvoie rien, l'opération a réussi.


#### Ajouter un seul moissonnage

Soit `my_harvest_name` l'identifiant - `name` - du moissonnage dans le répertoire.

```python
ckan = Ckan()
ckan.dev.harvest_action('create', harvest_name=my_harvest_name)
```

Le moissonnage en tant que tel sera lancé à la prochaine activation du cron. S'il est pertinent de l'activer plus tôt, cf. [Forcer l'exécution d'un seul moissonnage](#forcer-lexécution-dun-seul-moissonnage). S'il est souhaitable que ce moissonnage soit exécuté avant ou après d'autres, il peut également être préférable de relancer tous les moissonnages dans l'ordre du répertoire - cf. [Exécuter tous les moissonnages dans l'ordre](#exécuter-tous-les-moissonnages-dans-lordre)

Si la fonction ne renvoie rien, l'opération a réussi.


#### Mettre à jour un seul moissonnage

Il s'agit-là de modifier les paramètres du moissonnage. **La commande suivante n'a pas pour effet de relancer le moissonnage** (sur ce point, cf. [Forcer l'exécution d'un seul moissonnage](#forcer-lexécution-dun-seul moissonnage)).

Soit `my_harvest_name` l'identifiant - `name` - du moissonnage dans le répertoire.

```python
ckan = Ckan()
ckan.dev.harvest_action('patch', harvest_name=my_harvest_name)
```

*NB : on préfère `'patch'` à `'update'`, ici, car la structure du répertoire est stable (pas de priorités qui seraient susceptibles d'être supprimées) et cela permet de préserver certaines informations calculées automatiquement par CKAN.*

Si la fonction ne renvoie rien, l'opération a réussi.


#### Supprimer un seul moissonnage

La suppression des moissonnages passe par une fonction spécifique, `harvest_erase`, car elle implique plusieurs actions successives pour que les jeux de données liés soient également détruits et que les identifiants - `name` - redeviennent disponibles.

Soit `my_harvest_name` l'identifiant - `name` - du moissonnage dans le répertoire.

```python
ckan = Ckan()
ckan.dev.harvest_erase(harvest_name=my_harvest_name)
```

Si la fonction ne renvoie rien, l'opération a réussi.


#### Forcer l'exécution d'un seul moissonnage

Soit `my_harvest_name` l'identifiant - `name` - du moissonnage dans le répertoire.

```python
ckan = Ckan()
ckan.dev.run_harvest_job(harvest_name=my_harvest_name)
```

Si la fonction ne renvoie rien, l'opération a réussi.


#### Exécuter tous les moissonnages dans l'ordre

```python
ckan = Ckan()
ckan.dev.run_all_harvest_jobs()
```

Si la fonction ne renvoie rien, l'opération a réussi.

Cette fonction est lente, car pour garantir que les moissonnages s'effectuent dans le bon ordre, elle attend 5s[^sleep] après chaque ordre d'exécution.

[^sleep]: Valeur par défaut. Cette durée peut être modifiée (y compris mise à 0) avec l'argument `sleep_duration` de la fonction.


### Suivi de l'exécution des moissonnages

Il est possible d'exporter dans le répertoire [ckan_stats](/organisations/ckan_stats) un tableau récapitulatif de l'état des moissonnages de l'instance :
- dans le fichier [moissonnages_dev.md](/organisations/ckan_stats/moissonnages_dev.md) pour l'environnement de développement ;
- dans le fichier [moissonnages_preprod.md](/organisations/ckan_stats/moissonnages_preprod.md) pour l'environnement de pré-production ;
- dans le fichier [moissonnages_prod.md](/organisations/ckan_stats/moissonnages_prod.md) pour l'environnement de production.

```python
ckan = Ckan()
ckan.dev.harvest_summary(export=True)
```


## Syntaxe des filtres

La syntaxe des filtres OGC - objets de classe `OgcFilter` - et des conditions élémentaires qui les composent découle : 
- de la syntaxe attendue par les fonctions de la bibiothèque OWSLib (cf. [explications dans la documentation de la fonction `owslib.fes.setConstraintList()`](https://github.com/geopython/OWSLib/blob/master/owslib/fes.py#L129)) utilisée par ckanext-spatial pour les requêtes sur les serveurs CSW ;
- du fait que les configurations des moissonnages sont fournies en JSON, les filtres doivent par conséquent avoir une forme aisément sérialisable dans ce format.

*En aval, la dé-sérialisation des filtres est réalisée par la fonction `ckanext.spatial.lib.ogcfilter.parse_constraints()` ajoutée à ckanext-spatial. Pour faciliter la réalisation des tests lors de la génération des moissonnages, le fichier [ogcfilter.py](https://github.com/ecolabdata/ckanext-spatial/blob/master/ckanext/spatial/lib/ogcfilter.py) a été [copié](https://github.com/ecolabdata/guichetdonnees/blob/main/organisations/ogcfilter.py) dans le présent entrepôt.*

### Conditions élémentaires

Une **condition élémentaire** est une liste dont la longueur et la composition dépend de la nature de la condition, laquelle est définie par le premier élément de la liste.

Composition de la liste selon la nature de la condition :

| 0 | 1 | 2 | 3 |
| --- | --- | --- | --- |
| `'PropertyIsLike'` | Nom de la propriété (*str*) | Chaîne de caractères recherchée (*str*) | |
| `'PropertyIsNull'` | Nom de la propriété (*str*) | | |
| `'PropertyIsBetween'` | Nom de la propriété (*str*) | Valeur de début (*str* représentant une date ou *int* ou *float*) | Valeur de fin (idem) |
| `'PropertyIsGreaterThanOrEqualTo'` | Nom de la propriété (*str*) | Valeur (*str* représentant une date ou *int* ou *float*) | |
| `'PropertyIsLessThanOrEqualTo'` | Nom de la propriété (*str*) | Valeur (*str* représentant une date ou *int* ou *float*) | |
| `'PropertyIsGreaterThan'` | Nom de la propriété (*str*) | Valeur (*str* représentant une date ou *int* ou *float*) | |
| `'PropertyIsLessThan'` | Nom de la propriété (*str*) | Valeur (*str* représentant une date ou *int* ou *float*) | |
| `'PropertyIsNotEqualTo'` | Nom de la propriété (*str*) | Valeur (*str* ou *int* ou *float*) | |
| `'PropertyIsEqualTo'` | Nom de la propriété (*str*) | Valeur (*str* ou *int* ou *float*) | |
| `'BBox'` | Liste de coordonnées (*list* de *int* ou *float*)[^bbox]  | | |

[^bbox]: Minimum en X, minimum en Y, maximum en X, maximum en Y.

Exemple :
```python
elem = ["PropertyIsLike", "OrganisationName", "DDTM"]
```

En somme, le premier élément de la liste est le nom de la classe d'OWSLib et les éléments suivants sont les paramètres obligatoires de la fonction d'initialisation, avec le bon type et dans le bon ordre (arguments positionnels). Lorsque l'opérateur admet des paramètres optionnels[^optparam], ils peuvent être fournis dans un dictionnaire ajouté en fin de liste, dont les clés sont les noms des paramètres et les valeurs leurs valeurs.

[^optparam]: Cf. [documentation du module `owslib.fes`](https://github.com/geopython/OWSLib/blob/master/owslib/fes.py).

Exemple :
```python
elem = ["PropertyIsLike", "OrganisationName", "DDTM", {"matchCase": False}]
``` 

### Négation d'une condition

Pour nier une condition supplémentaire, il faut ajouter `"Not"` au début de la liste.

Exemple :
```python
elem = ["Not", "PropertyIsLike", "OrganisationName", "DDTM"]
```

### Assemblage des conditions

Un filtre OGC est une liste juxtaposant - opérateur `OR` :
- des conditions élémentaires ;
- ou des listes combinant - opérateur `AND` - des conditions élémentaires.

Cette syntaxe permet de représenter n'importe quel assemblage de conditions, mais toujours sous une forme entièrement développée.

### Exemples

On recherche une DDT - une seule condition :
```python
ogc_filter = [["PropertyIsLike", "OrganisationName", "DDT"]]
```

On recherche une DDT ou une DREAL - `condition 1 OR condition 2` :
```python
ogc_filter = [
    ["PropertyIsLike", "OrganisationName", "DDT"],
    ["PropertyIsLike", "OrganisationName", "DREAL"]
    ]
```

On recherche la DDT de la Corrèze - `condition 1 AND condition 2` :
```python
ogc_filter = [ # liste extérieure -> OR
    [ # liste interne -> AND
        ["PropertyIsLike", "OrganisationName", "DDT"],
        ["PropertyIsLike", "OrganisationName", "Corrèze"]
        ]
    ]
```

On recherche la DDT de la Corrèze ou la DDT du Puy-de-Dôme - `(condition 1 AND condition 2) OR (condition 3 AND condition 4 AND condition 5)` :
```python
ogc_filter = [ # liste extérieure -> OR
  [ # liste interne -> AND
      ["PropertyIsLike", "OrganisationName", "DDT"],
      ["PropertyIsLike", "OrganisationName", "Corrèze"]
      ],
  [ # liste interne -> AND
      ["PropertyIsLike", "OrganisationName", "DDT"],
      ["PropertyIsLike", "OrganisationName", "Dôme"],
      ["PropertyIsLike", "OrganisationName", "Puy"]
      ]
  ]
```

