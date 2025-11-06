#pragma once
#include "model_25.h"

class UIComponent25 {
public:
    UIComponent25();
    void render();
    void setModel(Model25* model);
private:
    Model25* model_;
};
