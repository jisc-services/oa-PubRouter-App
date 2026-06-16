"""
Blueprints for pages about the website linked to in the footer
"""
from flask import Blueprint, render_template

blueprint = Blueprint('website', __name__)


@blueprint.route('/cookies/', methods=['GET'])
def cookies():
    return render_template('website/cookies.html', title='Cookie Settings')


@blueprint.route('/accessibility/', methods=['GET'])
def accessibility():
    return render_template('website/accessibility.html', title='Accessibility Statement')

