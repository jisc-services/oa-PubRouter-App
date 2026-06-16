# JPER SWORD OUT Core Models

This application provides only a small number of models in order to track and persist the state of repositories
and the deposits against them.

* [SWORD status & credentials](./RepositorySwordDataModel.md) - the current known state of the repository, recording whether it is failing to accept deposits or if there are any current active problems with depositing.  It allows the workflow to determine whether to make a deposit at that time or not. It also stores the ID and Timestamp of the last notification processed. NOTE: This data is actually stored as part of the Router Repository Organisation Account record (in the _account_ table)

* [SWORD Deposit Record](./SwordDepositRecord.md) - for each deposit attempt, record timestamp and the result of each element of the deposit (metadata deposit, binary deposit, and completion). This data is stored in the _sword_deposit_ table. 
