"""
Institution identifier model file
"""
from router.shared.mysql_dao import IdentifierDAO
from octopus.lib import dataobj


class Identifier(dataobj.DataObj, IdentifierDAO):
    """
    {
        "type": "<id type, like 'JISC' or 'CORE'>",
        "value": "<actual id value>",
        "name": "<name of institution relating to corresponding id>"
    }
    """

    @property
    def value(self):
        return self._get_single("value")

    @value.setter
    def value(self, val):
        self._set_single("value", val, coerce=str)

    @property
    def type(self):
        return self._get_single("type")

    @type.setter
    def type(self, val):
        self._set_single("type", val, coerce=str)

    @property
    def name(self):
        return self._get_single("name")

    @name.setter
    def name(self, val):
        self._set_single("name", val, coerce=str)

    @classmethod
    def delete_all_by_type(cls, type, commit=True):
        """
        Simple query to delete all documents with a given type.

        :param type: Type of identifiers to delete
        :param commit: Boolean - whether to commit after deletion or not
        :return: Int - num records deleted
        """
        return cls.delete_by_query(type, del_name="all_of_type", commit=commit)

    @classmethod
    def reload_type_by_identifier_iterable(cls, iterable, type):
        """
        Update a type of identifier by something that can be iterated over.

        :param iterable: Iterable object which returns indexable items (lists, sets, tuples)
            Each member of the iterable must have the following as the first 3 elements:
                Identifier type: "JISC" or "CORE"
                Institution name - Name of institution
                Id - Numeric identifier value
        :param type: String type of corresponding identifiers to update - e.g. "JISC" or "CORE"
        """
        try:
            num_loaded = 0
            cls.start_transaction()

            # Delete entries from Identifiers index that match the specified type
            cls.delete_all_by_type(type, commit=False)

            id_dict = {"type": type}

            type_ix = None
            id_ix = None
            name_ix = None
            first_data = False  # Boolean to indicate if have processed first data row
            # Loop for each row of data
            for row in iterable:
                # Skip blank lines
                if len(row) == 0:
                    continue
                # Row is NOT expected list or tuple
                if isinstance(row, str):
                    if first_data:
                        # We are expecting at least 2 columns of data
                        raise ValueError(f"Got only 1 element in the row: {row}")
                    continue

                # Skip first row if the 3rd column (ID) does NOT contain a digit - assume it is heading row
                if not first_data:
                    # iterate over the columns in the row - decide what kind of data is in each column and set the
                    # index variables (id_ix, type_ix, name_ix) accordingly
                    for ix, col in enumerate(row):
                        # If column is all digits - assume it is the Identifier column
                        if col.isdigit():
                            id_ix = ix
                        elif col in ("JISC", "CORE"):       # Must be identifier type colukn
                            type_ix = ix
                        else:   # Assume column contains the Name
                            name_ix = ix
                    # Must have set both the id_ix and name_ix if we have found first data row
                    if id_ix is None:
                        # Reset any values that may be been set
                        type_ix = name_ix = None
                        # Get next row in iterable
                        continue
                    else:
                        if name_ix is not None:
                            first_data = True
                        else:
                            raise ValueError(f"Identifier found without a corresponding name in row: {row}")

                try:
                    # We are only loading data matching required type
                    if type_ix is not None and row[type_ix] != type:
                        continue

                    id_dict["name"] = row[name_ix]   # Second column contains Institution Name
                    id = row[id_ix]     # First column contains Identifier
                    id_dict["value"] = id
                except IndexError:
                    raise ValueError(f"Got fewer than 2 mandatory elements in the row: {row}")
                cls(id_dict).insert(commit=False)
                num_loaded += 1
            if not first_data:
                raise ValueError("Did not find any expected data in file: Instituion name, Numeric ID and, optionally, identifier type ('SWORD' or 'JISC')")
        except Exception as e:
            cls.rollback()
            raise e
        else:
            cls.commit()
        return num_loaded

    @classmethod
    def identifiers_to_csv_list(cls):
        """
        Sort all of the identifiers in ES, then return them in a csv-writable format.

        The list is sorted by order of type first, then each type is sorted by name ascending.

        :return: List of identifiers writable by csv.writer.
        """
        # Create list with header
        csv = [["Type", "Name", "ID"]]
        for identifier in cls.pull_all(pull_name="all"):
            csv.append([identifier.type, identifier.name, identifier.value])
        return csv

    @classmethod
    def search_by_name(cls, name, type=None):
        """
        Simple fuzzy search through names and if given, certain types.

        :param name: part of institution name to fuzzy search with
        :param type: Type of institution ID. Default to Wildcard

        :return: List of class objects for all institutions found.
        """
        return cls.pull_all(type if type else "%",      # Use wildcard to match all types if type is None
                            f"%{name}%",        # Construct wildcard string
                            pull_name="all_of_type_wildcard")
