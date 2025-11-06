#pragma once
#include "model_22.h"

class UIComponent22 {
public:
    UIComponent22();
    void render();
    void setModel(Model22* model);
private:
    Model22* model_;
};
