import bcrypt
import jwt
from datetime import datetime

from flask import current_app

from api.exceptions.badrequest import BadRequestException
from api.exceptions.validation import ValidationException

from neo4j.exceptions import ConstraintError

class AuthDAO:
    """
    The constructor expects an instance of the Neo4j Driver, which will be
    used to interact with Neo4j.
    """
    def __init__(self, driver, jwt_secret):
        self.driver = driver
        self.jwt_secret = jwt_secret

    """
    This method should create a new User node in the database with the email and name
    provided, along with an encrypted version of the password and a `userId` property
    generated by the server.

    The properties also be used to generate a JWT `token` which should be included
    with the returned user.
    """
    # tag::register[]
    def register(self, email, plain_password, name):

        def create_user(tx, email, encrypted, name):
            return tx.run("""
                CREATE (u:User {
                    userId: randomUuid()
                    , email: $email
                    , password: $encrypted
                    , name: $name
                })
                RETURN u
            """
            , email=email
            , encrypted=encrypted
            , name=name
            ).single()

        encrypted = bcrypt.hashpw(plain_password.encode("utf8"), bcrypt.gensalt()).decode('utf8')

        try:
            with self.driver.session() as session:
                result = session.execute_write(create_user, email, encrypted, name)

            user = result['u']

            payload = {
                'userId': user['userId']
                , 'email': user['email']
                , 'name': user['name']
            }

            payload['token'] = self._generate_token(payload)

            return payload
        except ConstraintError as err:
            raise ValidationException(err.message, {'email': err.message})

        # TODO: Handle unique constraint error
        if email != "graphacademy@neo4j.com":
            raise ValidationException(
                f"An account already exists with the email address {email}",
                {"email": "An account already exists with this email"}
            )
    # end::register[]

    """
    This method should attempt to find a user by the email address provided
    and attempt to verify the password.

    If a user is not found or the passwords do not match, a `false` value should
    be returned.  Otherwise, the users properties should be returned along with
    an encoded JWT token with a set of 'claims'.

    {
      userId: 'some-random-uuid',
      email: 'graphacademy@neo4j.com',
      name: 'GraphAcademy User',
      token: '...'
    }
    """
    # tag::authenticate[]
    def authenticate(self, email, plain_password):

        def get_user(tx, email):
            result = tx.run("MATCH (u:User {email: $email}) RETURN u"
                            , email=email)
            
            first = result.single()

            if first is None:
                return None
            
            user = first.get('u')
            return user
        
        with self.driver.session() as session:
            user = session.execute_read(get_user, email=email)
        
        if user is None:
            return False
        
        if bcrypt.checkpw(plain_password.encode('utf-8'), user['password'].encode('utf-8')) is False:
            return False

        payload = {
            'userId': user['userId']
            , 'email': user['email']
            , 'name': user['name']
        }

        payload['token'] = self._generate_token(payload)

        return payload
        # TODO: Implement Login functionality
    # end::authenticate[]

    """
    This method should take the claims encoded into a JWT token and return
    the information needed to authenticate this user against the database.
    """
    # tag::generate[]
    def _generate_token(self, payload):
        iat = datetime.utcnow()

        payload["sub"] = payload["userId"]
        payload["iat"] = iat
        payload["nbf"] = iat
        payload["exp"] = iat + current_app.config.get('JWT_EXPIRATION_DELTA')

        return jwt.encode(
            payload,
            self.jwt_secret,
            algorithm='HS256'
        )
    # end::generate[]

    """
    This method will attemp to decode a JWT token
    """
    # tag::decode[]
    def decode_token(auth_token, jwt_secret):
        try:
            payload = jwt.decode(auth_token, jwt_secret)
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    # end::decode[]
