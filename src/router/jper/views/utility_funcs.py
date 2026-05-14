"""
Utility functions used in view files
"""
import math
from flask import current_app, flash

def get_page_details_from_request(request_args, default_page_num=1):
    """
    Extract page and page_size from request args or use defaults.  Page will be either >= 1 or None.
    :param request_args: The Args from the request object
    :param default_page_num: Default page number (can be None)
    :return: Tuple of integers (page, page_size) - NB. page can be None.
    """
    default_page_size = current_app.config.get("DEFAULT_LIST_PAGE_SIZE", 25)
    try:
        page = request_args.get("page", default_page_num)
        if page is not None:
            page = int(page)
            if page < 1:
                page = 1
        page_size = int(request_args.get("pageSize", default_page_size))
    except ValueError:
        flash("Invalid 'page' and/or 'pageSize' parameter specified - defaults used instead.", "error")
        return default_page_num, default_page_size
    return page, page_size


def calc_num_of_pages(page_size, total_recs=None):
    """
    Calculate the number of pages based on page_size and total recs found
    :param  page_size: Integer - number of recs to display per page
    :param  total_recs: Integer - total number of recs for query
    :return: Int - number of pages or 0
    """
    return math.ceil(total_recs / page_size) if total_recs is not None else 0


