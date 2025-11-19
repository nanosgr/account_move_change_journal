{
    "name": "Account Move Change Journal",
    "version": "18.0.1.1.0",
    "category": "Accounting",
    "summary": "Change journal of account moves with proper field recalculation",
    "author": "Vikingo Software SAS",
    "website": "",
    "license": "AGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizards/account_move_change_journal_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
