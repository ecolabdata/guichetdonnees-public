"""OGC filters handling.

This module provides a function, :py:func:`parse_constraints`,
to parse the parameter `ogcfilter` of the harvest source configuration
into some valid constraints list that can be passed as `constraints`
parameter of OWSLib's functions such as `getrecords2`.

Syntax of `ogcfilter` is similar to OWSLib's OgcExpression classes,
albeit suited to JSON encoding.

For example, this JSON configuration::

    {
        "ogcfilter": [
            ["PropertyIsLike", "MyProperty1", "MyValue1"],
            ["Not", "PropertyIsEqualTo", "MyProperty2", "MyValue2"]
        ]
    }

Will be interpreted as this OWSLib constraints list::

    [
        PropertyIsLike('MyProperty1', 'MyValue1'),
        Not([PropertyIsEqualTo('MyProperty2', 'MyValue2')])
    ]

OWSLib constraints lists are fully expanded and `ogcfilter` values
should be as well. Elements of the list are combined with ``OR``.
Each element can be an elementary condition (such as 
``PropertyIsLike("MyProperty1", "MyValue1")`` in OWSLib encoding
or ``["PropertyIsLike", "MyProperty1", "MyValue1"]`` in JSON
encoding) or a list of elementary conditions to combine with ``AND``.

Therefore:

    * ``[A]`` is a single elementary condition.
    * ``[A, B, C]`` equates to ``A`` or ``B`` or ``C``.
    * ``[[A, B, C]]`` equates to ``A`` and ``B`` and ``C``.
    * ``[A, [B, C], D]`` equates to ``A`` or ``B`` and ``C`` or ``D``.

Elementary conditions are encoded in JSON as lists.

The first element should be the name of a known OGC Filter operator,
listed in :py:data:`ogc_filter_operators` (case sensitive) :
``"PropertyIsLike"`` or ``"PropertyIsEqualTo"``or ``"BBox"``, *etc*.

Following elements are positional mandatory parameters for the
OWSLib operator, ordered and typed as expected by said operator::

    ["PropertyIsLike", "PropertyName", "Value"]

Last element may be a dict of named optional parameters for the
operator, such as::

    ["PropertyIsLike", "PropertyName", "Value", {"matchCase": false}]

To negate the operator, add ``'Not'`` as first element of the list::

    ["Not", "PropertyIsLike", "PropertyName", "Value"]

References
----------
Documentation of OWSLib `fes` module (on GitHub_). 

.. _GitHub: https://github.com/geopython/OWSLib/blob/master/owslib/fes.py

"""

from owslib.fes import PropertyIsLike, PropertyIsNull, \
    PropertyIsBetween, PropertyIsGreaterThanOrEqualTo,  \
    PropertyIsLessThanOrEqualTo, PropertyIsGreaterThan, \
    PropertyIsLessThan, PropertyIsNotEqualTo, \
    PropertyIsEqualTo, BBox, Not

ogc_filter_operators = [PropertyIsLike, PropertyIsNull, PropertyIsBetween,
    PropertyIsGreaterThanOrEqualTo, PropertyIsLessThanOrEqualTo, PropertyIsGreaterThan,
    PropertyIsLessThan, PropertyIsNotEqualTo, PropertyIsEqualTo, BBox]
"""List of OWSLib classes for OGC Filter operators.

"""

def as_owslib_expression(constraint):
    """Rewrite some elementary condition using OWSLib classes.

    Parameters
    ----------
    constraint : list
        A list representing some elementary constraint, such as::
            ['PropertyIsLike', 'PropertyName', 'Value']
    
    Returns
    -------
    owslib.fes.OgcExpression
        A valid elementary condition.
    
    Raises
    ------
    OgcFilterSyntaxError
        When `constraint` first element (or second if ``'Not'``
        is first) is not one of :py:data:`ogc_filter_operators`.
    OgcFilterParsingError
        When initialization of the OWSLib object fails.
    
    """
    if not constraint:
        return  
    
    args = constraint.copy()
    
    neg = (args[0].lower() == 'not')
    if neg:
        del args[0]

    operator = {o.__name__: o for o in ogc_filter_operators}.get(args[0])
    if not operator:
        raise OgcFilterSyntaxError(constraint,
            detail="Unknow operator '{}'.".format(args[0]))
    del args[0]

    kwargs = {}
    if isinstance(args[len(args) - 1], dict):
        # optional parameters as dict
        kwargs = args.pop()

    try:
        res = operator.__call__(*args, **kwargs)
    except Exception as err:
        raise OgcFilterParsingError(constraint, err)
    
    if neg:
        res = Not([res])

    return res


def parse_constraints(ogcfilter):
    """Make a valid constraints list out of user-defined ogcfilter parameter.

    Result is intended for use as `constraints` parameter of
    OWSLib's functions such as `getrecords2`.

    Parameters
    ----------
    ogcfilter : list
        Parameter `ogcfilter` retrieved from user configuration.

    Raises
    ------
    OgcFilterSyntaxError
        If `ogcfilter` is not a list of elementary conditions
        or a list of lists of elementary conditions. 
    
    """
    if not isinstance(ogcfilter, list):
        raise OgcFilterSyntaxError(ogcfilter)
    
    ors = []
    
    for e in ogcfilter:
        if not isinstance(e, list):
            raise OgcFilterSyntaxError(ogcfilter)
        if isinstance(e[0], str):
            ors.append(as_owslib_expression(e))
        elif isinstance(e[0], list):
            ands = []
            for ee in e:
                if not isinstance(ee, list) or not isinstance(ee[0], str):
                    raise OgcFilterSyntaxError(ogcfilter)
                ands.append(as_owslib_expression(ee))
            ors.append(ands)
        else:
            raise OgcFilterSyntaxError(ogcfilter)
    
    return ors
    

class OgcFilterParsingError(Exception):
    """When some OWSLib call raises an error.
    
    Parameters
    ----------
    error : Exception
        Error raised by some OWSLib function.
    constraint : list
        Filter or part of filter for which the error was raised.
    
    Attributes
    ----------
    error : Exception
        Error raised by some OWSLib function.
    constraint : list
        Filter or part of filter for which the error was raised.
    
    """
    def __init__(self, constraint, error):
        self.error = error
        self.constraint = constraint
    
    def __str__(self):
        return "Couldn't parse filter element '{}'. " \
            "Raised {}.".format(self.constraint, self.error)


class OgcFilterSyntaxError(Exception):
    """When a filter is detected as malformed before any call to OWSLib.
    
    Parameters
    ----------
    constraint : list
        Filter or part of filter for which the
        exception was raised.
    detail : str, optional
        Specific message about the error.
    
    Attributes
    ----------
    constraint : list
        Filter or part of filter for which the
        exception was raised.
    detail : str
        Specific message about the error.
    
    """
    def __init__(self, constraint, detail=None):
        self.detail = detail
        self.constraint = constraint
    
    def __str__(self):
        detail = ' {}'.format(self.detail) if self.detail else ''
        return "Filter element '{}' is invalid.{}" \
            ''.format(self.constraint, detail)

