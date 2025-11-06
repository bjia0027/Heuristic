#pragma once
#include "model_4.h"

class UIComponent4 {
public:
    UIComponent4();
    void render();
    void setModel(Model4* model);
private:
    Model4* model_;
};
