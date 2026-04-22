'''
Created on 18 Nov 2015

Helper functions and class all pertaining to Harvester web service provider form, particularly defines WebserviceForm
which includes the specifications for a Harvester web service provider form

@author: Mateusz.Kasiuba
'''
import re
from datetime import datetime

from wtforms import Form, BooleanField, StringField, validators, SelectField, IntegerField, TextAreaField, ValidationError
from router.harvester.engine.GetEngine import engine_url_is_valid


def valid_url(form, url):

    if re.findall(r'pageSize=\d+', url.data):
        raise ValidationError("The 'pageSize' parameter is not allowed in the URL")

    if form.active.data:
        if not engine_url_is_valid(form.data['engine'], url.data):
            raise ValidationError(f"URL for {form.data['engine']} failed to return any results")

    return True


# Create a form for WEBSERVICE
class WebserviceForm(Form):

    def valid_date(self, date_field):
        """
        Private method - validate date
        """
        try:
            datetime.strptime(date_field.data, '%Y-%m-%d')
        except ValueError as e:
            raise ValidationError('Invalid date - expect YYYY-MM-DD format')
        return True

    id = StringField(
        'Webservice ID',
        render_kw={'disabled': True}
    )
    name = StringField(
        'Harvester name',
        [validators.Length(min=2, max=40), validators.DataRequired()],
        description="Unique name of harvester"
    )
    notes = TextAreaField(
        'Notes',
        [],
        description="Information about the harvester"
    )
    # URL must be TextAreaField (not URLField) because multi-line is essential for the long URLs
    url = TextAreaField(
        'Endpoint URL',
        [validators.Length(min=6, max=1024), validators.DataRequired(), valid_url],
        description=(
            "API endpoint with query parameters including place holders for {start_date} and {end_date} (if needed)"
        )
    )
    query = TextAreaField(
        'ES filter query',
        [validators.DataRequired()],
        description="Elasticsearch query used to filter results returned by API call"
    )
    end_date = StringField(
        'Start date',
        [validators.DataRequired(), valid_date],
        description="YYYY-MM-DD (date of next run)"
    )

    frequency_choices = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly')
    ]
    frequency = SelectField('Run frequency', choices=frequency_choices)

    engine_choices = [
        ('EPMC', 'EPMC'),
        ('PubMed', 'PubMed'),
        ('Crossref', 'Crossref'),
        ('Elsevier', 'Elsevier')
    ]
    engine = SelectField('Engine', choices=engine_choices)

    wait_window = IntegerField(
        'Harvest delayed by (days)',
        [validators.number_range(1, 90)],
        description="Number of days to wait"
    )
    active = BooleanField('Active')

    auto_enable = BooleanField('Auto-enable', description="Whether to automatically include harvester in new repo accounts data sources")

    # Some harvesters are shown to users as if they are a Publisher account (rather than a multi-publisher source)
    publisher = BooleanField('Show as publisher')

    # Live harvester accounts are visible to All users, not-Live visible ONLY to Admins
    live_date = StringField('Live')


# Form for showing number of repositories using the harvester webservice, and for disabling in all repos
class ServiceUsageForm(Form):
    # Total number of repositories (field is disabled - not editable)
    total_repos = IntegerField('Total repositories', render_kw={'disabled': True})

    # Number of repositories currently selecting a particular harvester as a source (field is disabled - not editable)
    num_using = IntegerField('Repos using this service', render_kw={'disabled': True})
