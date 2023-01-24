"""Définition des organisations."""

import json, requests
from pathlib import Path

from maintenance import __path__ as maintenance_path
from maintenance.config import (
    LOGO_BASE, DEFAULT_LOGO, REQUESTS_CONFIG
)

class Organization:
    """Une organisation.
    
    Parameters
    ----------
    name : str
        L'identifiant de l'organisation.
    title : str, optional
        Le libellé court de l'organisation. Cette information doit
        être renseignée à un moment ou un autre pour que
        l'organisation soit considérée comme valide, mais ce
        peut être après l'initialisation.
    label : str, optional
        Le libellé long de l'organisation. Cette information doit
        être renseignée à un moment ou un autre pour que
        l'organisation soit considérée comme valide, mais ce
        peut être après l'initialisation.
    description : str, optional
        La description de l'organisation. Cette information doit
        être renseignée à un moment ou un autre pour que
        l'organisation soit considérée comme valide, mais ce
        peut être après l'initialisation.
    image_url : str, optional
        Le chemin du logo de l'organisation. Cette information doit
        être renseignée à un moment ou un autre pour que
        l'organisation soit considérée comme valide, mais ce
        peut être après l'initialisation.
    groups : list(dict), optional
        Liste des organisations parentes. Une organisation
        est représentée par un dictionnaire dont l'unique clé
        ``name`` fournit l'identifiant de l'organisation.
    **kwargs
        Autres informations relatives à l'organisation. Cf.
        :py:data:`Organization.PROPERTY_LABELS` pour la liste
        des propriétés connues.
    
    Attributes
    ----------
    name : str
        L'identifiant de l'organisation.
    title : str
        Le libellé court de l'organisation.
    label : str or None
        Le libellé long de l'organisation.
    description : str or None
        La description de l'organisation.
    image_url : str
        Le chemin du logo de l'organisation.
    groups : list(dict)
        Liste des organisations parentes. Une organisation
        est représentée par un dictionnaire dont l'unique clé
        ``name`` fournit l'identifiant de l'organisation.
    extras : dict
        Métadonnées optionnelles.

    """

    PROPERTY_LABELS = {
        'email': 'Courriel',
        'phone': 'Téléphone',
        'page': 'Site internet',
        'territories': 'Territoire',
        'orgtype': 'Type'
    }

    @classmethod
    def property_from_label(cls, label):
        """Renvoie l'identifiant de la métadonnée optionnelle de libellé considéré, si elle existe.

        Parameters
        ----------
        label : str
            Le libellé de la métadonnée.

        Returns
        -------
        str

        """
        for property, plabel in cls.PROPERTY_LABELS.items():
            if plabel == label:
                return property

    COLLECTION = {}

    def __init__(
        self, name, title=None, label=None, description=None,
        image_url=None, groups=None, **kwargs
    ):
        if not name:
            raise ValueError('"name" should be provided')
        Organization.COLLECTION[name] = self
        self.name = name
        self.title = title
        self.label = label
        self.description = description
        self.image_url = image_url
        self.extras = {}
        groups = groups or []
        clean_groups = []
        for group in groups:
            if isinstance(group, str):
                clean_groups.append({'name': group})
            elif isinstance(group, dict) and 'name' in group:
                clean_groups.append({'name': group['name']})
            else:
                raise ValueError(f'invalid "groups" for organization {name}')
        self.groups = clean_groups
        for property, value in kwargs.items():
            if property == 'extras':
                for item in value:
                    try:
                        extra_value = json.loads(item['value'])
                    except:
                        extra_value = item['value']
                    self.set(
                        Organization.property_from_label(item['key']),
                        extra_value
                    )
            else:
                # laisse passer des métadonnées non déclarées
                # dans Organization.PROPERTY_LABELS, mais elles
                # seront détectées à la validation
                self.set(property, value)

    def __repr__(self):
        title = self.title or '?'
        return f'Organization < {self.name} | {title} >'

    @classmethod
    def search(cls, name):
        """Renvoie l'organisation d'identifiant considéré, si répertoriée.

        Parameters
        ----------
        name : str or None
            L'identifiant de l'organisation.

        """
        return cls.COLLECTION.get(name)

    @classmethod
    def update(cls, name, property, value):
        """Met à jour une propriété de l'organisation d'identifiant considéré.
        
        Parameters
        ----------
        name : str
            L'identifiant de l'organisation.
        property : str
            L'identifiant de la métadonnée.
        value : str or dict or list
            La valeur de la métadonnée. Il peut s'agir
            d'un littéral, d'un dictionnaire de traductions,
            d'une liste de dictionnaires de traductions ou
            d'une liste de valeurs littérales. Elle n'est
            pas contrôlée.

        Raises
        ------
        ValueError
            Si l'organisation n'est pas répertoriée.

        """
        org = cls.search(name)
        if not org:
            raise ValueError(f'organisation {name} non répertoriée')
        org.set(property, value)

    @classmethod
    def clear(cls):
        """Vide le répertoire des organisations."""
        cls.COLLECTION.clear()

    @classmethod
    def dump(cls, file=None):
        """Exporte le répertoire d'organisations.

        Si `file` n'est pas fourni, la méthode remplace le fichier
        ``organizations.json``.

        Parameters
        ----------
        file : pathlib.Path or str, optional
            Chemin du fichier à créer ou remplacer.

        """
        if file:
            file_path = Path(file)
        else:
            data_path = Path(maintenance_path[0]).parent
            file_path = data_path / 'organizations.json'
        
        data = json.dumps(
            {name: org.dict for name, org in cls.COLLECTION.items()},
            ensure_ascii=False,
            indent=4
        )
        file_path.write_text(data,encoding='utf-8')

    @classmethod
    def load(cls, file=None, url=None, append=True, **kwargs):
        """Charge les organisations depuis une source externe.

        La source doit être un JSON de structure identique
        à celui produit par :py:meth:`Organization.dump`.

        Si ni `file` ni `url` n'est renseigné, la méthode
        tente de charger les organisations depuis le fichier
        ``organizations.json``.

        Parameters
        ----------
        file : pathlib.Path or str, optional
            Chemin du fichier contenant le JSON.
        url : str, optional
            URL du JSON.
        append : bool, default True.
            Si ``True`` les organisations définies par la source
            sont ajoutées à celles déjà répertoriées. Si ``False``,
            le répertoire est vidé avant d'être reconstitué
            à partir de la source. Dans les deux cas les organisations
            communes au répertoire courant et à la source sont remplacées
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
        else:
            if file:
                file_path = Path(file)
                if not file_path.exists() or not file_path.is_file():
                    raise FileNotFoundError(f'file "{file}" not found')
            else:
                file_path = Path(maintenance_path[0]).parent / 'organizations.json'
                if not file_path.exists() or not file_path.is_file():
                    return
            raw = file_path.read_text(encoding='utf-8')
            data = json.loads(raw)
        if not append:
            cls.clear()
        for org in data:
            Organization(**data[org])

    def auto_image_url(self):
        """Génère l'URL standard du logo stocké sur le registre Ecosphères.
        
        La fonction vérifie si le logo est
        effectivement disponible sur le registre, sinon
        elle affecte le logo par défaut :py:data:`DEFAULT_LOGO`.

        Returns
        -------
        str

        """
        for image_format in ('svg', 'png', 'jpg'):
            image_url = f'{LOGO_BASE}/{self.name}.{image_format}'
            response = requests.get(image_url, **REQUESTS_CONFIG)
            try:
                response.raise_for_status()
                return image_url
            except:
                continue
        return DEFAULT_LOGO

    @classmethod
    def update_all_image_url(cls):
        """Met à jour les URL des logos pour toutes les organisations."""
        for org in cls.COLLECTION.values():
            org.image_url = org.auto_image_url()

    def validate(self, silent=False):
        """Vérifie la validité de l'organisation.
        
        Concrètement, une organisation sera présumée valide
        si elle a au moins un libellé court et long, un descriptif,
        un logo et un territoire associé, que toutes ses
        métadonnées additionnelles sont déclarées, et que tous
        les éventuels groupes auxquels elle appartient existent
        dans le registre.

        Parameters
        ----------
        silent : bool
            Si ``True``, la méthode renvoie ``False``
            en cas d'anomalie au lieu de générer une
            erreur.

        Returns
        -------
        bool
            ``True`` si l'organisation est valide.

        Raises
        ------
        ValueError
            À la première anomalie rencontrée.

        """
        err = None
        if not self.name:
            err = ValueError('identifiant manquant (name)')
        elif not self.title:
            err = ValueError(f'{self.name} : libellé court manquant (title)')
        elif not self.label:
            err = ValueError(f'{self.name} : libellé long manquant (label)')
        elif not self.description:
            err = ValueError(f'{self.name} : descriptif manquant (description)')
        elif not self.image_url:
            err = ValueError(f'{self.name} : logo manquant (image_url)')
        elif not self.territories:
            err = ValueError(f'{self.name} : territoire de compétence manquant (territories)')
        elif self.groups:
            for group in self.groups:
                parent = group.get('name')
                if not parent in Organization.COLLECTION:
                    err = ValueError(f'{self.name} : organisation parente "{parent}" inconnue (groups)')
                    break
        else:
            for key in self.extras:
                if not key in Organization.PROPERTY_LABELS:
                    err = ValueError(f'{self.name} : métadonnée "{key}" non déclarée')
                    break

        if err:
            if silent:
                return False
            raise err

        response = requests.get(self.image_url, **REQUESTS_CONFIG)
        if silent:
            return False
        response.raise_for_status()

        return True

    @property
    def dict(self):
        """dict: Dictionnaire des métadonnées de l'organisation.
        
        Peut être utilisé tel quel pour créer ou mettre à jour
        l'organisation via l'API de CKAN.

        """
        self.validate()
        d = {
            'name': self.name,
            'title': self.title,
            'label': self.label,
            'image_url': self.image_url,
            'description': self.description,
            'extras': []
        }
        if self.groups:
            d['groups'] = self.groups
        for key, value in self.extras.items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            d['extras'].append(
                {
                    'key': Organization.PROPERTY_LABELS.get(key, key),
                    'value': value
                }
            )
        return d

    def get(self, property):
        """Renvoie la valeur d'une métadonnée optionnelle.
        
        Parameters
        ----------
        property : str
            L'identifiant de la métadonnée.

        """
        return self.extras.get(property)

    def set(self, property, value):
        """Définit la valeur d'une métadonnée optionnelle.

        Parameters
        ----------
        property : str
            L'identifiant de la métadonnée.
        value : str or dict or list
            La valeur de la métadonnée. Il peut s'agir
            d'un littéral, d'un dictionnaire de traductions,
            d'une liste de dictionnaires de traductions ou
            d'une liste de valeurs littérales. Elle n'est
            pas contrôlée.

        """
        if not value:
            if property in self.extras:
                del self.extras[property]
            return
        self.extras[property] = value

    @property
    def email(self):
        """str: Courriel de l'organisation."""
        return self.get('email')

    @email.setter
    def email(self, value):
        self.set('email', value)
    
    @property
    def phone(self):
        """str: Numéro de téléphone de l'organisation."""
        return self.get('phone')

    @phone.setter
    def phone(self, value):
        self.set('phone', value)
    
    @property
    def page(self):
        """str: Site internet de l'organisation."""
        return self.get('page')

    @page.setter
    def page(self, value):
        self.set('page', value)
    
    @property
    def orgtype(self):
        """str: Type de l'organisation."""
        return self.get('orgtype')

    @orgtype.setter
    def orgtype(self, value):
        self.set('orgtype', value)

    @property
    def territories(self):
        """list(str): Territoires de compétence de l'organisation.
        
        Le setter de la propriété prend en argument un territoire
        ou une liste de territoires, qui remplaceront la liste courante.
        Pour ajouter un territoire sans supprimer les autres, on
        utilisera :py:meth:`Organization.add_territory`.

        """
        return self.extras.get('territories')

    @territories.setter
    def territories(self, value):
        if value:
            if isinstance(value, str):
                value = [str]
            else:
                value = list(value)
                value.sort()
        self.set('territories', value)

    def add_territory(self, territory):
        """Ajoute un territoire à la liste des territoires de compétence de l'organisation.
        
        Parameters
        ----------
        territory : str
            Un identifiant de territoire.

        """
        if not territory:
            return
        
        if not 'territories' in self.extras:
            self.territories = territory
        else:
            self.extras['territories'].append(territory)
            self.extras['territories'].sort()

    def remove_territory(self, territory):
        """Supprime un territoire de la liste des territoires de compétence de l'organisation.
        
        Parameters
        ----------
        territory : str
            Un identifiant de territoire.
        
        """
        if not territory:
            return
        
        if 'territories' in self.extras:
            while territory in self.extras['territories']:
                self.extras['territories'].remove(territory)

