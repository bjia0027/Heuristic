#pragma once
#include "service_25.h"
#include "model_25.h"
#include <memory>

class Controller25 {
public:
    Controller25();
    void initialize();
    void run();
private:
    std::unique_ptr<Service25> service_;
    std::shared_ptr<Model25> model_;
};
