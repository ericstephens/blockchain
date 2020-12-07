import hashlib
import json
from time import time
from urllib.parse import urlparse

import redis

class Blockchain:

    NODES = "nodes"
    CHAIN = "chain"

    def __init__(self):
        self.__current_transactions = []
        self.__redis = redis.Redis(host='192.168.1.168', decode_responses=True)
        
        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)

    def get_block(self,i):
        return json.loads(self.__redis.lindex(Blockchain.CHAIN,i))

    def add_block(self,block):
        return self.__redis.rpush(Blockchain.CHAIN,json.dumps(block))

    def get_length(self):
        return self.__redis.llen(Blockchain.CHAIN)

    # retrieve the whole chain
    def get(self):
        return self.__redis.lrange(Blockchain.CHAIN,0,-1)

    @property
    def current_transactions(self):
        return self.__current_transactions

    @property
    def last_block(self):
        return self.get_block(-1)

    def reset_transactions(self):
        self.__current_transactions = []

    def get_nodes(self):
        return self.__redis.smembers(Blockchain.NODES)

    def get_node_count(self):
        return self.__redis.scard(Blockchain.NODES)

    def node_exists(self,node):
        return self.__redis.sismember(Blockchain.NODES,node)

    def register_node(self, address):
        """
        Add a new node to the list of nodes

        :param address: Address of node. Eg. 'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        address_new = None

        if parsed_url.netloc:
            address_new = parsed_url.netloc
        elif parsed_url.path:
            # Accepts an URL without scheme like '192.168.0.5:5000'.
            address_new = parsed_url.path
        else:
            raise ValueError('Invalid URL')
        
        self.__redis.sadd(Blockchain.NODES, address_new)

    def valid_chain(self, chain):
        """
        Determine if a given blockchain is valid

        :param chain: A blockchain
        :return: True if valid, False if not
        """

        last_block = self.get_block(0)
        current_index = 1

        while current_index < len(chain):
            block = self.get_block(current_index)
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            last_block_hash = self.hash(last_block)
            if block['previous_hash'] != last_block_hash:
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof'], last_block_hash):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is our consensus algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.

        :return: True if our chain was replaced, False if not
        """

        neighbours = self.get_nodes()
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = self.get_length()

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False

    def new_block(self, proof, previous_hash):
        """
        Create a new Block in the Blockchain

        :param proof: The proof given by the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """

        block = {
            'index': self.get_length() + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.get_block(-1)),
        }

        # Reset the current list of transactions
        self.reset_transactions()

        self.add_block(block)
        return block

    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block

        :param sender: Address of the Sender
        :param recipient: Address of the Recipient
        :param amount: Amount
        :return: The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        return self.last_block['index'] + 1

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block

        :param block: Block
        """

        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def proof_of_work(self, last_block):
        """
        Simple Proof of Work Algorithm:

         - Find a number p' such that hash(pp') contains leading 4 zeroes
         - Where p is the previous proof, and p' is the new proof
         
        :param last_block: <dict> last Block
        :return: <int>
        """

        last_proof = last_block['proof']
        last_hash = self.hash(last_block)

        proof = 0
        while self.valid_proof(last_proof, proof, last_hash) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
        """
        Validates the Proof

        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :param last_hash: <str> The hash of the Previous Block
        :return: <bool> True if correct, False if not.

        """

        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"