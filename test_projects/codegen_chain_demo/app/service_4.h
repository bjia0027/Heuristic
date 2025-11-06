#pragma once
#include <functional>
#include <vector>

class Service4 {
public:
    Service4();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
