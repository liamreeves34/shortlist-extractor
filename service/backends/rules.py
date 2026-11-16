from service.schemas import ExtractRequest, ExtractResponse, FieldName, FieldResult, CONTRACT_VERSION, ALL_FIELDS
from service.settings import Settings
import re
# class ExtractResponse(BaseModel):
#     contract_version: str = CONTRACT_VERSION
#     backend: str
#     model_version: str
#     fields: dict[FieldName, FieldResult]
#     warnings: list[str] = []

settings = Settings()

class RulesBackend():
    name = "rules"
    model_name = "rules-1"
    
    
    
    def extract(self, req: ExtractRequest) -> ExtractResponse:
        warnings = []
        fields = []
        if not req.fields:           # if there is nothing in the list this will evaluate to false
            fields = ALL_FIELDS      # get all fields
        else:
            for i in req.fields:    # check if the elements in given fields are accepted
                if i in FieldName:  # if so, add them to list
                    fields.append(i)
                else:               # if not, say so
                    print(f"{i} is not an acceptable field")
        fields = tuple(fields)
                
            
        
        return ExtractResponse(
            contract_version=CONTRACT_VERSION,
            backend=settings.EXTRACTOR_BACKEND,
            model_version=self.model_name,
            fields={},
            warnings = warnings
        )
        
    

    def get_title(self):
        return
    def get_org(self):
        return
    def get_location(self):
        return
    def get_start_term(self):
        return
    def get_deadline(self):
        return
    def get_deadline_type(self):
        return
    def get_citizenship(self):
        return
    def get_clearance(self):
        return
    def get_work_mode(self):
        return
    def get_pay(self):
        return
    def get_skills(self):
        return