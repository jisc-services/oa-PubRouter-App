"""
Defines a "child" data object, a data object which inherits the save method and id of it's parent.

For example, RepositoryData is a child of AccOrg. This allows us to save a RepositoryData object independent of 
the account it is a child of. It also allows us to access id independently. So if we have
acc = AccOrg()
repo_data = acc.repository_data
repo_data.id == acc.id   # True
repo_data.grants = ["HHBB1122", "HHBBNNOO"]
repo_data.insert()   # is equivalent to acc.insert()
repo_data.update()   # is equivalent to acc.update()

"""
from octopus.lib.dataobj import DataObj

class DAOChild(DataObj):
    """
    Child inherits functions from parent.  Enclosures are used so that the life of the child object can persist even
    if the parent object goes out of scope.
    """

    @property
    def id(self):
        # take the id property of the parent (defined in __init__)
        return self._id_closure()

    def insert(self, *args, **kwargs):
        # take the insert method of the parent (defined in __init__)
        return self._insert_closure(*args, **kwargs)

    def update(self, *args, **kwargs):
        # take the update method of the parent (defined in __init__)
        return self._update_closure(*args, **kwargs)

    @property
    def parent(self):
        return self._parent_closure()

    def __init__(self, raw, parent):
        super().__init__(raw)

        def id():
            return parent.id

        def insert(*args, **kwargs):
            return parent.insert(*args, **kwargs)

        def update(*args, **kwargs):
            return parent.update(*args, **kwargs)

        def get_parent():
            return parent

        self._id_closure = id
        self._insert_closure = insert
        self._update_closure = update
        self._parent_closure = get_parent
