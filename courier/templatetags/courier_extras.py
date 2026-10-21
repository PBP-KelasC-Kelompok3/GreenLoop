from django import template

from courier.utils import get_initials

register = template.Library()


@register.filter
def initials(user):
    return get_initials(user)