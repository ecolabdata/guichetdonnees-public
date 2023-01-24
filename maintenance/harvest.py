"""Gestion des moissonnages."""

import json, requests
from pathlib import Path

from maintenance import __path__ as maintenance_path
from maintenance.config import (
    REQUESTS_CONFIG
)

class Harvest:
    """Une configuration de moissonnage.
    
    Attributes
    ----------
    url : str
        L'URL du catalogue.
    name : str
        Identifiant du moissonnage.
    owner_org : str
        Identifiant de l'organisation à laquelle est
        rattaché le moissonnage.
    source_type : {'dcat', 'csw', 'ckan'}
        Nature du moissonnage.
    title : str
        Libellé explicite du moissonnage.
    notes : str or None
        Observations libres.
    frequency : {'WEEKLY', 'MANUAL', 'MONTHLY', 'BIWEEKLY', 'DAILY', 'ALWAYS'}
        La fréquence de moissonnage.
    config : dict
        Configuration de moissonnage.
    
    See Also
    --------
    Pour les paramètres de configuration des moissonnages :
    https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/logic/action/create.py

    Pour les fréquences : 
    https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py

    """

    COLLECTION = {}

    def __init__(
        self, url, owner_org, source_type, title=None,
        name=None, notes=None, frequency='WEEKLY', **kwargs
    ):
        self.url = url
        self.owner_org = owner_org
        self.source_type = source_type
        self.notes = notes
        self.frequency = frequency
        if not name:
            i = 1
            while True:
                i_name = str(i).rjust(2, '0')
                beta_name = f'{owner_org}-h{i_name}'
                if not beta_name in Harvest.COLLECTION:
                    self.name = beta_name
                    break
                i += 1
        else:
            self.name = name
        self.config = {}
        for property, value in kwargs.items():
            if property == 'config':
                if isinstance(value, str):
                    config = json.loads(value)
                else:
                    config = value
                for conf_key, conf_value in config:
                    self.set(conf_key, conf_value)
            else:
                self.set(property, value)
    
    def __repr__(self):
        title = self.title or '?'
        return f'Harvest < {self.name} | {title} >'

    @classmethod
    def search(cls, name):
        """Renvoie le moissonnage d'identifiant considéré, si répertorié.

        Parameters
        ----------
        name : str or None
            L'identifiant du moissonnage.

        """
        return cls.COLLECTION.get(name)

    @classmethod
    def org_harvests(cls, owner_org):
        """Générateur sur les moissonnages d'une organisation.

        Parameters
        ----------
        owner_org : str
            L'identifiant de l'organisation.
            Correspond à l'attribut
            :py:attr:`maintenance.organization.Organization.name`.
        
        Yields
        ------
        Harvest

        """
        for harvest in cls.COLLECTION.values():
            if harvest.owner_org == owner_org:
                yield harvest
    
    @classmethod
    def update(cls, name, property, value):
        """Met à jour une propriété du moissonnage d'identifiant considéré.
        
        Parameters
        ----------
        name : str
            L'identifiant du moissonnage.
        property : str
            L'identifiant de la métadonnée.
        value : str or dict or list
            La valeur de la métadonnée. Elle n'est
            pas contrôlée.

        Raises
        ------
        ValueError
            Si le moissonnage n'est pas répertorié.

        """
        harvest = cls.search(name)
        if not harvest:
            raise ValueError(f'moissonnage {name} non répertorié')
        harvest.set(property, value)
    
    @classmethod
    def clear(cls, source_type=None):
        """Vide le répertoire des moissonnages.
        
        Parameters
        ----------
        source_type : str, optionnal
            Si fourni, seuls les moissonnages du type
            considérés sont supprimés.

        """
        if not source_type:
            cls.COLLECTION.clear()
        else:
            copy_collection = cls.COLLECTION.copy()
            for harvest_name, harvest in copy_collection.items():
                if harvest.source_type == source_type:
                    del cls.COLLECTION[harvest_name]

    @classmethod
    def dump(cls, directory=None, source_type=None):
        """Exporte le répertoire des moissonnages.

        Si `directory` n'est pas fourni, la méthode remplace
        les fichiers du répertoire ``harvests``, qu'elle crée
        si besoin. Il y a un fichier par type de source.

        Parameters
        ----------
        directory : pathlib.Path or str, optional
            Chemin du répertoire d'export. Il sera créé
            s'il n'existe pas.
        source_type : str, optionnal
            Si fourni, seuls les moissonnages du type
            considéré sont exportés.

        """
        if directory:
            dir_path = Path(directory)
            if not dir_path.exists() or not dir_path.is_dir():
                dir_path.mkdir()
        else:
            data_path = Path(maintenance_path[0]).parent
            dir_path = data_path / 'harvests'
        
        src_collection = {}
        for harvest in cls.COLLECTION.values():
            if source_type and not harvest.source_type == source_type:
                continue
            if harvest.source_type in src_collection:
                src_collection[harvest.source_type].append(harvest)
            else:
                src_collection[harvest.source_type] = [harvest]

        for src in src_collection:
            file_path = dir_path / f'{src}.json'
            data = json.dumps(
                {harvest.name: harvest.dict for harvest in src_collection},
                ensure_ascii=False,
                indent=4
            )
            file_path.write_text(data,encoding='utf-8')

    @classmethod
    def load(cls, directory=None, file=None, url=None, append=True, **kwargs):
        """Charge les moissonnages depuis une source externe.

        Les sources doivent être des JSON de structure identique
        à ceux produits par :py:meth:`Harvest.dump`. Les noms des
        fichiers n'ont aucune importance, mais la fonction ne
        considérera que ceux dont l'extension est `.json`.

        Si ni `directory`, ni `file` ni `url` n'est renseigné, la
        méthode tente de charger les organisations depuis les fichiers
        du répertoire `harvests`.

        Parameters
        ----------
        directory : pathlib.Path or str, optional
            Chemin du répertoire contenant les JSON. Tous les fichiers
            d'extension `.json` contenus dans ce répertoire seront
            considérés, quel que soit leur nom.
        file : pathlib.Path or str, optional
            Chemin du fichier contenant le JSON.
        url : str, optional
            URL du JSON.
        append : bool, default True.
            Si ``True`` les moissonnages définis par la source
            sont ajoutés à ceux déjà répertoriés. Si ``False``,
            le répertoire est vidé avant d'être reconstitué
            à partir de la source. Dans les deux cas les moissonnages
            communs au répertoire courant et à la source sont remplacés
            selon la source.
        **kwargs
            Paramètres additionnels à passer à la fonction
            :py:func:``open`` si la source est un fichier,
            ou à la fonction :py:func:``requests.get`` s'il
            s'agit d'une ressource web.

        """
        if url:
            params = REQUESTS_CONFIG.copy()
            params.update(kwargs)
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        elif file:
            file_path = Path(file)
            if not file_path.exists() or not file_path.is_file():
                raise FileNotFoundError(f'file "{file}" not found')
            raw = file_path.read_text(encoding='utf-8')
            data = json.loads(raw)
        else:
            if directory:
                dir_path = Path(directory)
                if not dir_path.exists() or not dir_path.is_dir():
                    raise FileNotFoundError(f'directory "{directory}" not found')
            else:
                dir_path = Path(maintenance_path[0]).parent / 'harvests'
                if not dir_path.exists() or not dir_path.is_dir():
                    return
            data = {}
            for harvest_file in dir_path.iterdir():
                if harvest_file.is_file() and harvest_file.suffix == '.json':
                    raw = file_path.read_text(encoding='utf-8')
                    file_data = json.loads(raw)
                    if isinstance(file_data, dict):
                        data.update(file_data)
                        print(f'retrieved harvest configurations from "{file_data}"')
        if not append:
            cls.clear()
        for org in data:
            Harvest(**data[org])

    @property
    def dict(self):
        """dict: Dictionnaire des métadonnées du moissonnage.
        
        Peut être utilisé tel quel pour créer ou mettre à jour
        le moissonnage via l'API de CKAN.

        """
        d = {
            'url': self.url,
            'name': self.name,
            'owner_org': self.owner_org,
            'title': self.title,
            'notes': self.notes,
            'source_type': self.source_type,
            'frequency': self.frequency
        }
        if self.config:
            d['config'] = json.dumps(self.config, ensure_ascii=False)
        return d
