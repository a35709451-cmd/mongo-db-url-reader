import re
import json
import pymongo
from pymongo import MongoClient
from bson import json_util, ObjectId
import urllib.parse
from datetime import datetime
import humanize

# Helper to mask credentials in MongoDB URI
def mask_mongo_url(url: str) -> str:
    try:
        # Match mongodb:// or mongodb+srv://
        match = re.match(r'(mongodb(?:\+srv)?://)([^/]+)', url)
        if not match:
            return "Invalid Connection String format"
        
        scheme = match.group(1)
        rest = match.group(2)
        
        # Check if auth details exist
        if '@' in rest:
            auth, host = rest.split('@', 1)
            if ':' in auth:
                user, password = auth.split(':', 1)
                masked_user = user[:2] + "***" if len(user) > 2 else "***"
                masked_auth = f"{masked_user}:****"
            else:
                masked_auth = auth[:2] + "***" if len(auth) > 2 else "***"
            return f"{scheme}{masked_auth}@{host}"
        return url
    except Exception:
        return "Hidden Connection String (Masking Failed)"

class MongoHelper:
    def __init__(self, uri: str, timeout_ms: int = 5000):
        self.uri = uri
        self.timeout_ms = timeout_ms
        self.client = None
    
    def connect(self):
        """Attempts connection and pings the database to verify it's active"""
        try:
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_ms,
                connectTimeoutMS=self.timeout_ms
            )
            # Trigger connection check
            self.client.admin.command('ping')
            return True, "Successfully connected!"
        except Exception as e:
            if self.client:
                self.client.close()
            return False, str(e)
            
    def close(self):
        if self.client:
            self.client.close()

    def get_server_info(self):
        """Retrieves server build information and stats"""
        try:
            build_info = self.client.admin.command('buildInfo')
            status_info = {}
            try:
                status_info = self.client.admin.command('serverStatus')
            except Exception:
                pass # Might not have admin rights for serverStatus
            
            info = {
                "version": build_info.get("version", "Unknown"),
                "gitVersion": build_info.get("gitVersion", "Unknown")[:8] + "...",
                "os": build_info.get("sysInfo", "Unknown"),
                "bits": build_info.get("bits", "Unknown"),
                "ok": build_info.get("ok", 0),
                "uptime": status_info.get("uptime", None),
                "connections": status_info.get("connections", {}).get("current", None),
                "network_bytes_in": status_info.get("network", {}).get("bytesIn", None),
                "network_bytes_out": status_info.get("network", {}).get("bytesOut", None)
            }
            return True, info
        except Exception as e:
            return False, str(e)

    def list_databases(self):
        """List all databases and their sizes"""
        try:
            db_list = self.client.list_database_names()
            dbs = []
            
            # Try to get database sizes
            try:
                db_infos = self.client.admin.command('listDatabases')
                size_map = {db['name']: db['sizeOnDisk'] for db in db_infos.get('databases', [])}
            except Exception:
                size_map = {}
                
            for name in db_list:
                size = size_map.get(name, 0)
                readable_size = humanize.naturalsize(size) if size else "Unknown Size"
                dbs.append({"name": name, "size": size, "readable_size": readable_size})
                
            return True, sorted(dbs, key=lambda x: x['name'])
        except Exception as e:
            # Fallback if listDatabases fails due to auth restrictions
            try:
                db_list = self.client.list_database_names()
                dbs = [{"name": name, "size": 0, "readable_size": "Unknown (No Permission)"} for name in db_list]
                return True, sorted(dbs, key=lambda x: x['name'])
            except Exception as e2:
                return False, str(e2)

    def list_collections(self, db_name: str):
        """List collections in a database with doc counts and stats"""
        try:
            db = self.client[db_name]
            coll_names = db.list_collection_names()
            collections = []
            
            for coll_name in coll_names:
                try:
                    # Quick estimate of document count (fast, doesn't scan entire collection)
                    count = db[coll_name].estimated_document_count()
                except Exception:
                    try:
                        count = db[coll_name].count_documents({})
                    except Exception:
                        count = -1
                
                try:
                    stats = db.command("collStats", coll_name)
                    storage_size = stats.get("storageSize", 0)
                    readable_size = humanize.naturalsize(storage_size)
                except Exception:
                    readable_size = "Unknown"
                    
                collections.append({
                    "name": coll_name,
                    "count": count,
                    "readable_size": readable_size
                })
            return True, sorted(collections, key=lambda x: x['name'])
        except Exception as e:
            return False, str(e)

    def view_documents(self, db_name: str, coll_name: str, query: dict = None, skip: int = 0, limit: int = 5, sort_by: str = None, sort_order: int = pymongo.DESCENDING):
        """Fetch documents with pagination and sorting"""
        try:
            db = self.client[db_name]
            coll = db[coll_name]
            
            if query is None:
                query = {}
                
            cursor = coll.find(query).skip(skip).limit(limit)
            
            if sort_by:
                cursor = cursor.sort(sort_by, sort_order)
            else:
                cursor = cursor.sort("_id", pymongo.DESCENDING)
                
            docs = list(cursor)
            # Get total match count
            try:
                total_count = coll.count_documents(query)
            except Exception:
                total_count = "Unknown"
                
            # Serialize using bson json_util to preserve ObjectId, datetime, etc.
            serialized_docs = json.loads(json_util.dumps(docs))
            return True, {"documents": serialized_docs, "total": total_count}
        except Exception as e:
            return False, str(e)

    def execute_query(self, db_name: str, coll_name: str, query_str: str, skip: int = 0, limit: int = 5):
        """Execute a custom find query from JSON string"""
        try:
            query_dict = json.loads(query_str, object_hook=json_util.object_hook)
            return self.view_documents(db_name, coll_name, query=query_dict, skip=skip, limit=limit)
        except Exception as e:
            return False, f"JSON Parse Error: {str(e)}"

    def execute_aggregation(self, db_name: str, coll_name: str, pipeline_str: str):
        """Execute a custom aggregation pipeline from JSON array string"""
        try:
            pipeline = json.loads(pipeline_str, object_hook=json_util.object_hook)
            if not isinstance(pipeline, list):
                return False, "Aggregation pipeline must be a JSON array (list)."
                
            db = self.client[db_name]
            coll = db[coll_name]
            
            results = list(coll.aggregate(pipeline))
            serialized_results = json.loads(json_util.dumps(results[:20])) # Limit to first 20 in UI
            return True, {"results": serialized_results, "total": len(results)}
        except Exception as e:
            return False, f"Pipeline Error: {str(e)}"

    def insert_document(self, db_name: str, coll_name: str, doc_str: str):
        """Insert a document from JSON string"""
        try:
            doc_dict = json.loads(doc_str, object_hook=json_util.object_hook)
            db = self.client[db_name]
            coll = db[coll_name]
            result = coll.insert_one(doc_dict)
            return True, f"Document inserted successfully. ID: {result.inserted_id}"
        except Exception as e:
            return False, str(e)

    def update_document(self, db_name: str, coll_name: str, doc_id_str: str, update_str: str):
        """Update a document by its ID (ID can be ObjectId or raw string)"""
        try:
            # Parse ID
            doc_id = doc_id_str
            if doc_id_str.startswith("ObjectId('") and doc_id_str.endswith("')"):
                raw_id = doc_id_str[10:-2]
                doc_id = ObjectId(raw_id)
            elif len(doc_id_str) == 24 and all(c in "0123456789abcdefABCDEF" for c in doc_id_str):
                try:
                    doc_id = ObjectId(doc_id_str)
                except Exception:
                    pass
            else:
                # Try parsing as JSON to check if it's an int, or dict
                try:
                    doc_id = json.loads(doc_id_str)
                except Exception:
                    pass

            update_dict = json.loads(update_str, object_hook=json_util.object_hook)
            
            # Ensure proper update operators (like $set)
            if not any(k.startswith('$') for k in update_dict.keys()):
                update_dict = {"$set": update_dict}
                
            db = self.client[db_name]
            coll = db[coll_name]
            result = coll.update_one({"_id": doc_id}, update_dict)
            
            if result.matched_count == 0:
                return False, f"No document matched the ID: {doc_id_str}"
            return True, f"Modified {result.modified_count} document(s)."
        except Exception as e:
            return False, str(e)

    def delete_document(self, db_name: str, coll_name: str, doc_id_str: str):
        """Delete a document by ID"""
        try:
            doc_id = doc_id_str
            if doc_id_str.startswith("ObjectId('") and doc_id_str.endswith("')"):
                raw_id = doc_id_str[10:-2]
                doc_id = ObjectId(raw_id)
            elif len(doc_id_str) == 24 and all(c in "0123456789abcdefABCDEF" for c in doc_id_str):
                try:
                    doc_id = ObjectId(doc_id_str)
                except Exception:
                    pass
            else:
                try:
                    doc_id = json.loads(doc_id_str)
                except Exception:
                    pass
                    
            db = self.client[db_name]
            coll = db[coll_name]
            result = coll.delete_one({"_id": doc_id})
            
            if result.deleted_count == 0:
                return False, f"No document matched ID: {doc_id_str}"
            return True, "Document deleted successfully."
        except Exception as e:
            return False, str(e)

    def export_collection(self, db_name: str, coll_name: str, limit: int = 50000):
        """Exports full collection up to safety limit as pretty-printed JSON"""
        try:
            db = self.client[db_name]
            coll = db[coll_name]
            
            docs = list(coll.find().limit(limit))
            # Serialize using bson json_util to handle dates/ObjectIds properly
            json_data = json_util.dumps(docs, indent=2)
            return True, json_data
        except Exception as e:
            return False, str(e)

    def get_indexes(self, db_name: str, coll_name: str):
        """List indexes of a collection"""
        try:
            db = self.client[db_name]
            coll = db[coll_name]
            indexes = coll.index_information()
            return True, indexes
        except Exception as e:
            return False, str(e)

    def create_index(self, db_name: str, coll_name: str, keys_str: str, unique: bool = False):
        """Create a new index. keys_str format: field1:1,field2:-1"""
        try:
            index_keys = []
            for key_part in keys_str.split(','):
                field, direction = key_part.split(':')
                index_keys.append((field.strip(), int(direction.strip())))
                
            db = self.client[db_name]
            coll = db[coll_name]
            index_name = coll.create_index(index_keys, unique=unique)
            return True, f"Index created successfully: {index_name}"
        except Exception as e:
            return False, str(e)

    def drop_index(self, db_name: str, coll_name: str, index_name: str):
        """Drop a collection index by name"""
        try:
            db = self.client[db_name]
            coll = db[coll_name]
            coll.drop_index(index_name)
            return True, f"Index '{index_name}' dropped successfully."
        except Exception as e:
            return False, str(e)

    def drop_collection(self, db_name: str, coll_name: str):
        """Drops a collection from database"""
        try:
            db = self.client[db_name]
            db.drop_collection(coll_name)
            return True, f"Collection '{coll_name}' dropped successfully."
        except Exception as e:
            return False, str(e)

    def drop_database(self, db_name: str):
        """Drops a database entirely"""
        try:
            self.client.drop_database(db_name)
            return True, f"Database '{db_name}' dropped successfully."
        except Exception as e:
            return False, str(e)

    def create_collection(self, db_name: str, coll_name: str):
        """Create a collection in a database"""
        try:
            db = self.client[db_name]
            db.create_collection(coll_name)
            return True, f"Collection '{coll_name}' created successfully."
        except Exception as e:
            return False, str(e)
            
    def clone_collection(self, db_name: str, source_coll: str, target_coll: str):
        """Clones documents from source_coll to target_coll"""
        try:
            db = self.client[db_name]
            # Verify target doesn't exist to prevent accidental overwrite
            if target_coll in db.list_collection_names():
                return False, f"Target collection '{target_coll}' already exists."
                
            docs = list(db[source_coll].find())
            if not docs:
                db.create_collection(target_coll)
                return True, f"Source collection was empty. Empty target collection '{target_coll}' created."
                
            result = db[target_coll].insert_many(docs)
            return True, f"Cloned {len(result.inserted_ids)} document(s) into '{target_coll}'."
        except Exception as e:
            return False, str(e)
