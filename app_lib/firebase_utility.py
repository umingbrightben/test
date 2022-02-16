import logging

from firebase_admin import auth, firestore, exceptions
from fastapi import HTTPException, status

# Setting Logger
LOGGER = logging.getLogger(__name__)


class FireBaseLoader():
    def __init__(self):
        self.db = firestore.client()

    def get_uid_by_email(self, email):
        """ Get uid from firebase by email """
        login_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login info",
        )
        try:
            user = auth.get_user_by_email(email)
        except auth.UserNotFoundError:
            LOGGER.error('Specified user does not exist, username: %s', email)
            raise login_exception
        except exceptions.FirebaseError as ex:
            LOGGER.error('Firebase error')
            LOGGER.error(ex)
            raise login_exception
        return user.uid

    def get_data_by_uid(self, uid):
        """ Get data from firestore by uid """
        doc_ref = self.db.collection("UserData").document(uid)
        docs = doc_ref.get()
        if docs.exists:
            return docs.to_dict()
        else:
            LOGGER.error("Can not access firebase, collection: UserData, uid: %s", uid)
            raise HTTPException(status_code=500, detail='Get firebase data error.')

    def get_data_by_email(self, email):
        """ Get data from firestore by email """
        uid = self.get_uid_by_email(email)
        res_data = self.get_data_by_uid(uid)
        return res_data

    def get_all_data(self):
        """ Get all data from firestore """
        docs = self.db.collection("UserData").stream()
        res_data = []
        for doc in docs:
            res_data.append(doc.to_dict())
        return res_data

    def get_data_by_org(self, org):
        """ Get all user data with org """
        docs = self.db.collection("UserData").where('organization', '==', org).stream()
        res_data = []
        for doc in docs:
            res_data.append(doc.to_dict())
        return res_data

    def set_data_by_uid(self, uid, user_info):
        """ Set new user info data to firestore """
        self.db.collection("UserData").document(uid).set(user_info)
        return

    def update_data_by_uid(self, uid, user_info):
        """ Update user info data to firestore """
        self.db.collection("UserData").document(uid).update(user_info)
        return

    def delete_data_by_uid(self, uid):
        """ Delete a user info data from firestore """
        self.db.collection("UserData").document(uid).delete()
        return

    def create_user(self, user_info: dict):
        """ Create user with user info """
        try:
            user = auth.create_user(email=user_info.get('email'), password=user_info.get('password'))
            return user
        except auth.EmailAlreadyExistsError:
            LOGGER.error('Specified user email is already exist, user email: %s', user_info.get('email'))
            raise HTTPException(status_code=400, detail='New user email is exist in firebase')

    def update_user_password(self, uid, user_password):
        user = auth.update_user(uid, password=user_password)
        return user

    def delete_user(self, uid: str):
        """ Delete user by uid """
        LOGGER.info("Delete uid from firebase, uid: %s", uid)
        auth.delete_user(uid)
        return

    def delete_user_by_list(self, uid_list: list):
        """ Delete user by uid list """
        LOGGER.info("Delete uid from firebase, uid_list:")
        LOGGER.info(uid_list)
        result = auth.delete_users(uid_list)
        for err in result.errors:
            LOGGER.error("Error # %s, reason: %s", result.index, result.reason)
        return
