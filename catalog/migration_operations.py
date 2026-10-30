from django.db.migrations.operations.base import Operation


class AddMissingFields(Operation):
    """Add fields only when the merged database does not already have them."""

    reduces_to_sql = False
    reversible = True

    def __init__(self, model_keys):
        self.model_keys = model_keys

    def deconstruct(self):
        return (self.__class__.__name__, [self.model_keys], {})

    def state_forwards(self, app_label, state):
        pass

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        connection = schema_editor.connection
        table_names = set(connection.introspection.table_names())
        for model_app, model_name in self.model_keys:
            model = to_state.apps.get_model(model_app, model_name)
            table = model._meta.db_table
            try:
                old_model = from_state.apps.get_model(model_app, model_name)
            except LookupError:
                old_model = None
            if table not in table_names:
                schema_editor.create_model(model)
                table_names.add(table)
                continue
            old_names = {field.name for field in old_model._meta.local_fields} if old_model else set()
            columns = {column.name for column in connection.introspection.get_table_description(schema_editor.connection.cursor(), table)}
            for field in model._meta.local_fields:
                if field.name not in old_names and field.column not in columns:
                    schema_editor.add_field(model, field)
                    columns.add(field.column)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Keep columns that may have been created by the other side of the merge.
        pass

    def describe(self):
        return "Add missing catalog fields while merging migration histories"
