"""This module provides a conversion layer for data types passed to/from
   Geoprocessing tasks on an ArcGIS REST server."""

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        raise ImportError("Please install the simplejson module "\
                          "from http://www.undefined.org/python/ "\
                          "or use arcrest with Python 2.6")

import datetime
import geometry

class GPBaseType(object):
    """Base type for Geoprocessing argument types"""
    class __metaclass__(type):
        def __init__(cls, name, bases, dict):
            type.__init__(name, bases, dict)
            try:
                if '|' not in cls.__name__:
                    GPBaseType._gp_type_mapping[cls.__name__] = cls
            except:
                pass
    #: Mapping from Geoprocessing type to name
    _gp_type_mapping = {}

    def __str__(self):
        return json.dumps(self._json_struct)
    @classmethod
    def _from_json_def(cls, json):
        return cls

class GPSimpleType(GPBaseType):
    """For geoprocessing types that simplify to base Python types, such as 
       int, bool, or string."""
    __conversion__ = None
    def __init__(self, val):
        self.value = val
    @property
    def _json_struct(self):
        return self.__conversion__(self.value)
    @classmethod
    def from_json_struct(cls, value):
        return cls.__conversion__(value)

class GPBoolean(GPSimpleType):
    """Represents a geoprocessing boolean parameter"""
    __conversion__ = bool

class GPDouble(GPSimpleType):
    """Represents a geoprocessing double parameter"""
    __conversion__ = float

class GPLong(GPSimpleType):
    """Represents a geoprocessing long parameter"""
    __conversion__ = long

class GPString(GPSimpleType):
    """Represents a geoprocessing long parameter"""
    __conversion__ = str

class GPLinearUnit(GPBaseType):
    """Represents a geoprocessing linear unit parameter"""
    #: The set of unit names allowed, defaulting to esriMeters
    allowed_units = set(['esriCentimeters',
                         'esriDecimalDegrees',
                         'esriDecimeters',
                         'esriFeet',
                         'esriInches',
                         'esriKilometers',
                         'esriMeters',
                         'esriMiles',
                         'esriMillimeters',
                         'esriNauticalMiles',
                         'esriPoints',
                         'esriUnknownUnits',
                         'esriYards'])
    def __init__(self, value, unit=None):
        if isinstance(value, (list, tuple)) and len(value) == 2:
            value, unit = value
        value = float(value)
        # Default to meters? Maybe take this out.
        if unit is None:
            unit = 'esriMeters'
        else:
            assert unit in self.allowed_units, "Unit %r not valid" % unit
        self.distance, self.units = value, unit
    @property
    def _json_struct(self):
        return {'distance': self.distance, 'units': self.units}
    @classmethod
    def from_json_struct(cls, val):
        return cls(val['distance'], val['units'])

class GPFeatureRecordSetLayer(GPBaseType):
    """Represents a geoprocessing feature recordset parameter"""
    def __init__(self, Geometry, sr=None):
        if isinstance(Geometry, geometry.Geometry):
            Geometry = [Geometry]
        self.features = Geometry
        if sr:
            self.spatialReference = geometry.SpatialReference(sr)
        elif len(self.features):
            self.spatialReference = geometry.SpatialReference(
                                        self.features[0].spatialReference)
        else:
            raise ValueError("Could not determine spatial reference")
        self.fields = set()
        for row in self.features:
            map(self.fields.add, set(getattr(row, 'attributes', {}).keys()))
    @property
    def _json_struct(self):
        geometry_types = set(geom.__geometry_type__ for geom in self.features)
        assert len(geometry_types) == 1, "Must have consistent geometries"
        geometry_type = list(geometry_types)[0]
        return {
                    'geometryType': geometry_type,
                    'spatialReference': self.spatialReference._json_struct,
                    'features': [
                        x._json_struct_for_featureset for x in self.features]
               }
    @classmethod
    def from_json_struct(cls, value):
        spatialreference = geometry.convert_from_json(value['spatialReference'])
        geometries = [geometry.convert_from_json(geo['geometry'], 
                                                 geo['attributes']) 
                        for geo in value['features']]
        return cls(geometries, spatialreference)

class GPRecordSet(GPBaseType):
    """Represents a geoprocessing recordset parameter"""
    def __init__(self, arg):
        self.features = arg

class GPDate(GPBaseType):
    """Represents a geoprocessing date parameter. The format parameter
       in the object constructor varies from the REST API's format parameters
       in that each date field in the format string must be preceded by a
       percent sign, as in the strftime function. For further information
       about Python strftime format strings, please refer to
       http://docs.python.org/library/time.html#time.strftime"""
    __date_format = "%a %b %d %H:%M:%S %Z %Y"

    def __init__(self, date, format="%Y-%m-%d"):
        if isinstance(date, basestring):
            try:
                self.date = datetime.datetime.strptime(date, format)
            except:
                self.date = datetime.datetime.strptime(date, self.__date_format)
        elif isinstance(date, (datetime.date, datetime.datetime)):
            self.date = date
        else:
            raise ValueError("Cannot convert %r to a date" % date)
        self.format = format
    @property
    def _json_struct(self):
        return {'date': self.date.strftime(self.format),
                'format': self.format.replace('%', '')}
        #return self.date.strftime(self.__date_format)
    @classmethod
    def from_json_struct(cls, value):
        if isinstance(value, dict):
            datestring = value['date']
            formatstring = value['format']
            # Re-escape field names from formats like Y-m-d back to
            # strftime-style %Y-%m-%d strings
            for chr in "%aAbBcdHIjmMpSUwWxXyYZ":
                formatstring = formatstring.replace(chr, '%'+chr)
            return cls(datestring, formatstring)
        elif isinstance(value, basestring):
            return cls(value, cls.__date_format)

class GPDataFile(GPBaseType):
    """A URL for a geoprocessing data file parameter"""
    #: The URL of the data file
    url = ''
    def __init__(self, url):
        self.url = url
    def _json_struct(self):
        return {'url': self.url}
    @classmethod
    def from_json_struct(cls, value):
        return cls(value['url'])

class GPUrlWithFormatType(GPBaseType):
    """A class for representing Raster data and Raster layers -- both have a 
       URL and a Format attribute."""
    #: The URL of the resource
    url = ''
    #: The data format of the raster: jpeg, png, etc.
    format = ''
    def __init__(self, url, format):
        self.url, self.format = url, format
    @property
    def _json_struct(self):
        return {'url': self.url, 'format': self.format}
    @classmethod
    def from_json_struct(cls, value):
        return cls(value['url'], value['format'])

class GPRasterData(GPUrlWithFormatType):
    """A URL for a geoprocessing raster data file parameter, with format."""

class GPRasterLayer(GPUrlWithFormatType):
    """A URL for a geoprocessing raster data layer file parameter,
       with format."""
