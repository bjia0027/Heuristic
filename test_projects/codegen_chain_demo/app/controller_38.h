#pragma once
#include "service_38.h"
#include "model_38.h"
#include <memory>

class Controller38 {
public:
    Controller38();
    void initialize();
    void run();
private:
    std::unique_ptr<Service38> service_;
    std::shared_ptr<Model38> model_;
};
