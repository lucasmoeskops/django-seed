import random

from django.db.models import ForeignKey, ManyToManyField, OneToOneField
from django.db.models.fields import AutoField

from django_seed.exceptions import SeederException
from django_seed.guessers import NameGuesser, FieldTypeGuesser

class ModelSeeder(object):
    def __init__(self, model):
        """
        :param model: Generator
        """
        self.model = model
        self.field_formatters = {}

    @staticmethod
    def build_relation(field, related_model):
        def func(inserted):
            if related_model in inserted and inserted[related_model]:
                pk = random.choice(inserted[related_model])
                return related_model.objects.get(pk=pk)
            else:
                message = 'Field {} cannot be null'.format(field)
                raise SeederException(message)

        return func

    def guess_field_formatters(self, faker):
        """
        Gets the formatter methods for each field using the guessers
        or related object fields
        :param faker: Faker factory object
        """
        formatters = {}
        name_guesser = NameGuesser(faker)
        field_type_guesser = FieldTypeGuesser(faker)

        for field in self.model._meta.fields:

            field_name = field.name

            if field.get_default(): 
                formatters[field_name] = field.get_default()
                continue
            
            if isinstance(field, (ForeignKey, ManyToManyField, OneToOneField)):
                formatters[field_name] = self.build_relation(field, field.related_model)
                continue

            if isinstance(field, AutoField):
                continue

            if not field.choices:
                formatter = name_guesser.guess_format(field_name)
                if formatter:
                    formatters[field_name] = formatter
                    continue

            formatter = field_type_guesser.guess_format(field)
            if formatter:
                formatters[field_name] = formatter
                continue

        return formatters

    def execute(self, using, inserted_entities):
        """
        Execute the stages entities to insert
        :param using:
        :param inserted_entities:
        """

        def format_field(format, inserted_entities):
            if callable(format):
                return format(inserted_entities)
            return format

        def turn_off_auto_add(model):
            for field in model._meta.fields:
                if getattr(field, 'auto_now', False):
                    field.auto_now = False
                if getattr(field, 'auto_now_add', False):
                    field.auto_now_add = False

        manager = self.model.objects.db_manager(using=using)
        turn_off_auto_add(manager.model)

        faker_data = {
            field: format_field(field_format, inserted_entities)
            for field, field_format in self.field_formatters.items()
        }

        # max length restriction check
        for data_field in faker_data:
            field = self.model._meta.get_field(data_field)

            if field.max_length and isinstance(faker_data[data_field], str):
                faker_data[data_field] = faker_data[data_field][:field.max_length]

        obj = manager.create(**faker_data)

        return obj.pk

    def repopulate(self, using, instance, inserted_entities):
        """
        Repopulate the given instance with random data
        :param using:
        :param inserted_entities:
        """

        def format_field(format, inserted_entities):
            if callable(format):
                return format(inserted_entities)
            return format

        def turn_off_auto_add(model):
            for field in model._meta.fields:
                if getattr(field, 'auto_now', False):
                    field.auto_now = False
                if getattr(field, 'auto_now_add', False):
                    field.auto_now_add = False

        manager = self.model.objects.db_manager(using=using)
        turn_off_auto_add(manager.model)

        faker_data = {
            field: format_field(field_format, inserted_entities)
            for field, field_format in self.field_formatters.items()
        }

        # max length restriction check
        for data_field in faker_data:
            field = self.model._meta.get_field(data_field)

            if field.max_length and isinstance(faker_data[data_field], str):
                faker_data[data_field] = faker_data[data_field][:field.max_length]

        manager.filter(pk=instance.pk).update(**faker_data)

        return instance.pk


class Seeder(object):
    def __init__(self, faker):
        """
        :param faker: Generator
        """
        self.faker = faker
        self.entities = {}
        self.quantities = {}
        self.orders = []
        self.instances = {}

    def add_entity(self, model, number, customFieldFormatters=None):
        """
        Add an order for the generation of $number records for $entity.

        :param model: mixed A Django Model classname,
        or a faker.orm.django.EntitySeeder instance
        :type model: Model
        :param number: int The number of entities to seed
        :type number: integer
        :param customFieldFormatters: optional dict with field as key and 
        callable as value
        :type customFieldFormatters: dict or None
        """
        if not isinstance(model, ModelSeeder):
            model = ModelSeeder(model)

        model.field_formatters = model.guess_field_formatters(self.faker)
        if customFieldFormatters:
            model.field_formatters.update(customFieldFormatters)
        
        klass = model.model
        self.entities[klass] = model
        self.quantities[klass] = number
        self.orders.append(klass)

    def add_instance(self, instance):
        klass = instance.__class__
        model = ModelSeeder(klass)

        if klass not in self.entities:
            self.add_entity(model, 0)

        if klass not in self.instances:
            self.instances[klass] = []

        self.instances[klass].append(instance)

    def execute(self, using=None):
        """
        Populate the database using all the Entity classes previously added.

        :param using A Django database connection name
        :rtype: A list of the inserted PKs
        """
        if not using:
            using = self.get_connection()

        inserted_entities = {}
        for klass in self.orders:
            number = self.quantities[klass]
            if klass not in inserted_entities:
                inserted_entities[klass] = []
            for i in range(0, number):
                entity = self.entities[klass].execute(using, inserted_entities)
                inserted_entities[klass].append(entity)
            for instance in self.instances[klass]:
                entity = self.entities[klass].repopulate(using, instance, inserted_entities)
                inserted_entities[klass].append(entity)

        return inserted_entities

    def get_connection(self):
        """
        use the first connection available
        :rtype: Connection
        """

        klass = self.entities.keys()
        if not klass:
            message = 'No classed found. Did you add entities to the Seeder?'
            raise SeederException(message)
        klass = list(klass)[0]

        return klass.objects._db
